"""唯一的 AIS 聚类主流程。

该模块只读取识别所需的四列 AIS 字段，并在读取每个文件时就筛选中国范围。
与旧脚本相比，聚类坐标转换改为 GeoPandas 的矢量化投影，不再逐行调用 UTM。
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely import concave_hull
from shapely.errors import TopologicalError
from shapely.geometry import box
from shapely.ops import unary_union
from sklearn.cluster import AgglomerativeClustering, DBSCAN

try:  # 支持 `python -m src.common.main` 与 `python src/common/main.py` 两种运行方式。
    from .paths import AIS_DATA_DIR, CHINA_SHP, COASTLINE_SHP, RESULTS_DIR, next_result_dir
except ImportError:  # pragma: no cover
    from paths import AIS_DATA_DIR, CHINA_SHP, COASTLINE_SHP, RESULTS_DIR, next_result_dir


INPUT_COLUMNS = ["MMSI", "BaseDateTime", "Latitude", "Longitude"]
INPUT_DTYPES = {"MMSI": "int64", "Latitude": "float64", "Longitude": "float64"}
BERTH_COLUMNS = [
    "cluster_id",
    "lat",
    "lon",
    "count",
    "dwell_minutes",
    "center_method",
    "type",
    "polygon",
]
ANCHORAGE_COLUMNS = [
    "cluster_id",
    "lat",
    "lon",
    "count",
    "dwell_minutes",
    "center_method",
    "radius_m",
    "type",
    "polygon",
]


@dataclass(frozen=True)
class PipelineConfig:
    stop_speed_kn: float = 1.0
    min_stop_minutes: int = 60
    berth_drift_max_m: float = 150.0
    anchorage_drift_min_m: float = 300.0
    anchorage_duration_min: int = 24 * 60
    berth_eps_m: float = 150.0
    berth_min_samples: int = 2
    berth_outline_buffer_m: float = 0.0
    anchorage_eps_m: float = 6000.0
    anchorage_min_samples: int = 5
    anchorage_max_span_m: float | None = None
    anchorage_shape_method: str = "concave_hull"
    anchorage_center_coverage_quantile: float = 0.5
    anchorage_concavity_ratio: float = 0.10
    anchorage_outline_buffer_m: float = 180.0
    anchorage_adaptive_buffer_min_m: float = 0.0
    anchorage_adaptive_buffer_max_m: float = 0.0
    anchorage_adaptive_buffer_span_ratio: float = 0.0
    anchorage_simplify_m: float = 40.0
    anchorage_exclude_terminal_overlap: bool = False
    anchorage_terminal_clearance_m: float = 0.0
    anchorage_exclude_land_overlap: bool = False
    anchorage_land_clearance_m: float = 0.0
    anchorage_use_land_boundary_distance: bool = False
    anchorage_open_water_only: bool = False
    berth_coast_max_m: float = 4000.0
    anchorage_coast_min_m: float = 3000.0
    anchorage_coast_max_m: float = 20000.0
    terminal_eps_m: float = 1000.0
    terminal_min_samples: int = 1
    terminal_max_span_m: float | None = None
    terminal_merge_buffer_m: float = 180.0
    terminal_outline_buffer_m: float = 0.0
    terminal_shape_method: str = "merged_outline"
    terminal_resolve_rectangle_overlaps: bool = False
    terminal_simplify_m: float = 35.0
    workers: int = 8
    china_lon_min: float = 73.0
    china_lon_max: float = 135.0
    china_lat_min: float = 18.0
    china_lat_max: float = 54.0


def haversine_m(lat1, lon1, lat2, lon2):
    """返回可广播数组之间的球面距离（米）。"""
    radius = 6_371_000.0
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * radius * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def _read_one_ship(path: Path, config: PipelineConfig) -> pd.DataFrame:
    """读取单个 CSV，并立即丢弃中国范围外的记录以降低内存压力。"""
    last_error = None
    for encoding in ("utf-8", "utf-8-sig", "gbk", "latin1"):
        try:
            frame = pd.read_csv(path, usecols=INPUT_COLUMNS, dtype=INPUT_DTYPES, encoding=encoding)
            frame = frame.dropna(subset=["MMSI", "BaseDateTime", "Latitude", "Longitude"])
            return frame.loc[
                frame["Longitude"].between(config.china_lon_min, config.china_lon_max)
                & frame["Latitude"].between(config.china_lat_min, config.china_lat_max)
            ]
        except UnicodeDecodeError as exc:
            last_error = exc
    raise RuntimeError(f"无法读取 AIS 文件：{path}") from last_error


def load_ais_data(config: PipelineConfig) -> pd.DataFrame:
    files = sorted(AIS_DATA_DIR.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"未在 {AIS_DATA_DIR} 找到 AIS CSV 文件")

    workers = min(config.workers, len(files))
    print(f"读取 {len(files)} 个 AIS 文件（{workers} 个线程，只保留中国范围和 4 个必要字段）")
    frames = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_read_one_ship, path, config) for path in files]
        for index, future in enumerate(as_completed(futures), start=1):
            frames.append(future.result())
            if index == len(files) or index % 20 == 0:
                print(f"已读取 {index}/{len(files)} 个 AIS 文件")

    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        raise ValueError("中国范围内没有有效 AIS 记录")
    data = pd.concat(frames, ignore_index=True, copy=False)
    print(f"保留 AIS 记录：{len(data):,}")
    return data


def prepare_ship_data(data: pd.DataFrame) -> pd.DataFrame:
    data = data.rename(
        columns={"BaseDateTime": "timestamp", "Latitude": "lat", "Longitude": "lon"}
    ).copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"], utc=True, errors="coerce")
    data = data.dropna(subset=["timestamp", "lat", "lon"])
    return data.sort_values(["MMSI", "timestamp"], kind="stable").reset_index(drop=True)


def detect_stops(data: pd.DataFrame, config: PipelineConfig) -> pd.DataFrame:
    data = data.copy()
    groups = data.groupby("MMSI", sort=False)
    data["lat_prev"] = groups["lat"].shift()
    data["lon_prev"] = groups["lon"].shift()
    data["time_prev"] = groups["timestamp"].shift()
    data["time_diff_s"] = (data["timestamp"] - data["time_prev"]).dt.total_seconds()
    data["distance_m"] = haversine_m(data["lat"], data["lon"], data["lat_prev"], data["lon_prev"])

    valid_interval = data["time_diff_s"].gt(0)
    data["speed_kn"] = np.where(
        valid_interval,
        data["distance_m"] / data["time_diff_s"] * 1.94384,
        np.inf,
    )
    data["stop"] = data["speed_kn"].lt(config.stop_speed_kn)
    data["stop_group"] = data.groupby("MMSI", sort=False)["stop"].transform(
        lambda value: value.ne(value.shift()).cumsum()
    )

    stops = (
        data.loc[data["stop"]]
        .groupby(["MMSI", "stop_group"], sort=False)
        .agg(
            lat=("lat", "mean"),
            lon=("lon", "mean"),
            start=("timestamp", "min"),
            end=("timestamp", "max"),
            lat_min=("lat", "min"),
            lat_max=("lat", "max"),
            lon_min=("lon", "min"),
            lon_max=("lon", "max"),
        )
        .reset_index()
    )
    stops["duration_min"] = (stops["end"] - stops["start"]).dt.total_seconds() / 60
    stops["drift_m"] = haversine_m(
        stops["lat_min"], stops["lon_min"], stops["lat_max"], stops["lon_max"]
    )
    stops = stops.loc[stops["duration_min"].ge(config.min_stop_minutes)].reset_index(drop=True)
    print(f"有效停泊段：{len(stops):,}")
    return stops


def classify_behavior(stops: pd.DataFrame, config: PipelineConfig) -> pd.DataFrame:
    stops = stops.copy()
    stops["behavior"] = "unknown"
    stops.loc[stops["drift_m"].lt(config.berth_drift_max_m), "behavior"] = "berth_like"
    stops.loc[
        stops["drift_m"].ge(config.anchorage_drift_min_m)
        & stops["duration_min"].ge(config.anchorage_duration_min),
        "behavior",
    ] = "anchorage_like"
    return stops


def _project_coordinates(frame: pd.DataFrame) -> np.ndarray:
    points = gpd.GeoDataFrame(
        frame, geometry=gpd.points_from_xy(frame["lon"], frame["lat"]), crs="EPSG:4326"
    ).to_crs("EPSG:3857")
    return np.column_stack((points.geometry.x.to_numpy(), points.geometry.y.to_numpy()))


def weighted_medoid_lon_lat(frame: pd.DataFrame) -> tuple[float, float]:
    """返回停留时长加权 medoid，保证中心是一个真实 AIS 停泊位置。

    普通均值或多边形质心可能落在两个泊位之间；medoid 则选择与同组活动
    总距离最小的实际停泊点。距离计算使用 EPSG:3857 米制坐标，并按
    `duration_min` 加权，使长时间靠泊比短暂停留更能代表中心。
    """
    if frame.empty:
        raise ValueError("无法从空数据计算中心")

    coordinates = _project_coordinates(frame)
    durations = (
        pd.to_numeric(frame["duration_min"], errors="coerce")
        if "duration_min" in frame
        else pd.Series(1.0, index=frame.index)
    )
    weights = np.nan_to_num(np.asarray(durations, dtype="float64"), nan=1.0, posinf=1.0)
    weights = np.maximum(weights, 1.0)

    # 分块计算距离矩阵，避免一个特别活跃的泊位聚类占用过多内存。
    scores = np.empty(len(frame), dtype="float64")
    block_size = 512
    for start in range(0, len(frame), block_size):
        stop = min(start + block_size, len(frame))
        offsets = coordinates[start:stop, None, :] - coordinates[None, :, :]
        distances = np.hypot(offsets[..., 0], offsets[..., 1])
        scores[start:stop] = distances @ weights

    center = frame.iloc[int(np.argmin(scores))]
    return float(center["lon"]), float(center["lat"])


def run_dbscan(frame: pd.DataFrame, eps_m: float, min_samples: int) -> pd.DataFrame:
    if frame.empty:
        return frame.assign(cluster=pd.Series(dtype="int64"))
    clustered = frame.copy()
    clustered["cluster"] = DBSCAN(eps=eps_m, min_samples=min_samples).fit_predict(
        _project_coordinates(clustered)
    )
    return clustered


def run_anchorage_clustering(frame: pd.DataFrame, config: PipelineConfig) -> pd.DataFrame:
    """聚类锚地，并可限制 DBSCAN 链式连通造成的单簇最大跨度。"""
    clustered = run_dbscan(frame, config.anchorage_eps_m, config.anchorage_min_samples)
    if clustered.empty or config.anchorage_max_span_m is None:
        return clustered

    initial = clustered["cluster"].to_numpy()
    coordinates = _project_coordinates(clustered)
    labels = np.full(len(clustered), -1, dtype="int64")
    next_label = 0
    for initial_label in np.unique(initial):
        indices = np.flatnonzero(initial == initial_label)
        if initial_label == -1:
            continue
        if len(indices) < config.anchorage_min_samples:
            continue
        split = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=config.anchorage_max_span_m,
            linkage="complete",
            metric="euclidean",
        ).fit_predict(coordinates[indices])
        for split_label in np.unique(split):
            split_indices = indices[split == split_label]
            if len(split_indices) < config.anchorage_min_samples:
                continue
            labels[split_indices] = next_label
            next_label += 1
    clustered["cluster"] = labels
    return clustered


def cluster_to_rectangles(clustered: pd.DataFrame, config: PipelineConfig) -> pd.DataFrame:
    records = []
    for cluster_id, group in clustered.loc[clustered["cluster"].ne(-1)].groupby("cluster", sort=True):
        min_lon, max_lon = group["lon"].min(), group["lon"].max()
        min_lat, max_lat = group["lat"].min(), group["lat"].max()
        center_lon, center_lat = weighted_medoid_lon_lat(group)
        outline = box(min_lon, min_lat, max_lon, max_lat)
        if config.berth_outline_buffer_m > 0:
            outline = (
                gpd.GeoSeries([outline], crs="EPSG:4326")
                .to_crs("EPSG:3857")
                .buffer(config.berth_outline_buffer_m, join_style=1)
                .to_crs("EPSG:4326")
                .iloc[0]
            )
        records.append(
            {
                "cluster_id": cluster_id,
                "lat": center_lat,
                "lon": center_lon,
                "count": len(group),
                "dwell_minutes": group["duration_min"].sum(),
                "center_method": "duration_weighted_stop_medoid",
                "type": "berth",
                "polygon": outline.wkt,
            }
        )
    return pd.DataFrame(records, columns=BERTH_COLUMNS)


def _regularize_geometry(geometry, merge_buffer_m: float, simplify_m: float):
    """合并相邻区域并简化边界，不使用会跨越空白区域的凸包。"""
    expanded = geometry.buffer(merge_buffer_m, join_style=2)
    regularized = expanded.buffer(-merge_buffer_m, join_style=2)
    if regularized.is_empty:
        regularized = geometry
    return regularized.simplify(simplify_m, preserve_topology=True)


def weighted_distance_quantile_m(
    frame: pd.DataFrame, center_lon: float, center_lat: float, quantile: float
) -> float:
    """返回到真实 AIS 中心的指定停泊时长加权距离分位数。"""
    if not 0 < quantile <= 1:
        raise ValueError("锚地中心覆盖分位数必须在 (0, 1] 内")
    coordinates = _project_coordinates(frame)
    center = _project_coordinates(pd.DataFrame({"lon": [center_lon], "lat": [center_lat]}))[0]
    distances = np.hypot(coordinates[:, 0] - center[0], coordinates[:, 1] - center[1])
    weights = np.maximum(pd.to_numeric(frame["duration_min"], errors="coerce").fillna(1.0), 1.0)
    order = np.argsort(distances)
    cumulative_weights = np.cumsum(np.asarray(weights)[order])
    quantile_index = np.searchsorted(cumulative_weights, cumulative_weights[-1] * quantile)
    return float(distances[order][quantile_index])


def cluster_to_anchorage_areas(clustered: pd.DataFrame, config: PipelineConfig) -> pd.DataFrame:
    """按指定方法生成锚地范围面。"""
    records = []
    for cluster_id, group in clustered.loc[clustered["cluster"].ne(-1)].groupby("cluster", sort=True):
        points_3857 = gpd.GeoDataFrame(
            group, geometry=gpd.points_from_xy(group["lon"], group["lat"]), crs="EPSG:4326"
        ).to_crs("EPSG:3857")
        center_points = unary_union(points_3857.geometry)
        if config.anchorage_shape_method == "concave_hull":
            area_3857 = concave_hull(
                center_points, ratio=config.anchorage_concavity_ratio, allow_holes=False
            )
            area_3857 = area_3857.buffer(config.anchorage_outline_buffer_m, join_style=2)
        elif config.anchorage_shape_method == "point_buffer_union":
            # 不使用凹包。以当前缓冲距离生成一个圆角外边界，让同一 DBSCAN
            # 锚地呈现为一片连续活动水域；随后再由陆地、码头排除规则裁切。
            # 这不改变锚地聚类、停泊判定或任何数值阈值。
            area_3857 = center_points.convex_hull.buffer(
                config.anchorage_outline_buffer_m, join_style=1
            )
            center_lon, center_lat = float(group["lon"].mean()), float(group["lat"].mean())
            center_method = "arithmetic_mean_stop_location"
            radius_m = np.nan
        elif config.anchorage_shape_method == "adaptive_point_buffer_union":
            # 按点群跨度自适应外扩：紧凑点群不被统一大缓冲放大，拉长的外海点群
            # 则保留足够的延伸范围。后续仍由陆地和码头掩膜裁掉不合理部分。
            hull = center_points.convex_hull
            bounds = hull.bounds
            span_m = float(np.hypot(bounds[2] - bounds[0], bounds[3] - bounds[1]))
            radius_m = float(
                np.clip(
                    span_m * config.anchorage_adaptive_buffer_span_ratio,
                    config.anchorage_adaptive_buffer_min_m,
                    config.anchorage_adaptive_buffer_max_m,
                )
            )
            area_3857 = hull.buffer(radius_m, join_style=1)
            center_lon, center_lat = float(group["lon"].mean()), float(group["lat"].mean())
            center_method = "arithmetic_mean_stop_location"
        elif config.anchorage_shape_method == "center_buffer":
            # 与码头中心相同：取停泊时长加权 medoid，保证中心是真实 AIS 停泊位置。
            # 半径为该中心的时长加权距离分位数；上限复用既有 6 km 锚地聚类半径。
            center_lon, center_lat = weighted_medoid_lon_lat(group)
            radius_m = min(
                max(
                    weighted_distance_quantile_m(
                        group,
                        center_lon,
                        center_lat,
                        config.anchorage_center_coverage_quantile,
                    ),
                    config.anchorage_outline_buffer_m,
                ),
                config.anchorage_eps_m,
            )
            center_3857 = gpd.GeoSeries(
                gpd.points_from_xy([center_lon], [center_lat]), crs="EPSG:4326"
            ).to_crs("EPSG:3857").iloc[0]
            area_3857 = center_3857.buffer(radius_m, join_style=1)
            center_method = "duration_weighted_stop_medoid"
        else:
            raise ValueError(f"未知锚地范围方法：{config.anchorage_shape_method!r}")
        area_3857 = area_3857.simplify(config.anchorage_simplify_m, preserve_topology=True)
        area_wgs84 = gpd.GeoSeries([area_3857], crs="EPSG:3857").to_crs("EPSG:4326").iloc[0]
        if config.anchorage_shape_method == "concave_hull":
            center_lon, center_lat = float(group["lon"].mean()), float(group["lat"].mean())
            center_method = "arithmetic_mean_stop_location"
            radius_m = np.nan
        records.append(
            {
                "cluster_id": cluster_id,
                "lat": center_lat,
                "lon": center_lon,
                "count": len(group),
                "dwell_minutes": group["duration_min"].sum(),
                "center_method": center_method,
                "radius_m": radius_m,
                "type": "anchorage",
                "polygon": area_wgs84.wkt,
            }
        )
    return pd.DataFrame(records, columns=ANCHORAGE_COLUMNS)


def get_china_coastline_line():
    coastline = gpd.read_file(COASTLINE_SHP)
    countries = gpd.read_file(CHINA_SHP)
    china = countries.loc[countries["NAME"].isin(["China", "Taiwan"])].unary_union
    return coastline.loc[coastline.intersects(china)].to_crs("EPSG:3857").unary_union


def add_coast_distance(frame: pd.DataFrame, coastline_3857) -> pd.DataFrame:
    if frame.empty:
        result = frame.copy()
        result["distance_to_coast"] = pd.Series(dtype="float64")
        return result
    points = gpd.GeoDataFrame(
        frame, geometry=gpd.points_from_xy(frame["lon"], frame["lat"]), crs="EPSG:4326"
    ).to_crs("EPSG:3857")
    result = frame.copy()
    result["distance_to_coast"] = points.geometry.distance(coastline_3857).to_numpy()
    return result


def add_land_flag(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        result = frame.copy()
        result["inside_china_land"] = pd.Series(dtype="bool")
        return result
    countries = gpd.read_file(CHINA_SHP)
    china = countries.loc[countries["NAME"].isin(["China", "Taiwan"])].to_crs("EPSG:3857").unary_union
    points = gpd.GeoDataFrame(
        frame, geometry=gpd.points_from_xy(frame["lon"], frame["lat"]), crs="EPSG:4326"
    ).to_crs("EPSG:3857")
    result = frame.copy()
    result["inside_china_land"] = points.geometry.within(china).to_numpy()
    return result


def get_china_land_geometry():
    countries = gpd.read_file(CHINA_SHP)
    return countries.loc[countries["NAME"].isin(["China", "Taiwan"])].to_crs("EPSG:3857").union_all()


def get_china_land_boundary():
    """返回陆地边界；包含国界面内部的河岸、岛岸，用于排除狭窄内河水道。"""
    return get_china_land_geometry().boundary


def terminal_cluster_labels(coordinates: np.ndarray, config: PipelineConfig) -> np.ndarray:
    """聚类泊位，并可限制单一码头在外扩前的最大空间跨度。

    DBSCAN 使用连通关系：一串每两点相距不足 eps 的泊位可能被连成很长的
    单一类别。`terminal_max_span_m` 启用后，只在既有 DBSCAN 类别内部使用
    complete linkage 再切分，确保每个子类的任意两泊位中心距离不超过该阈值。
    """
    initial = DBSCAN(
        eps=config.terminal_eps_m, min_samples=config.terminal_min_samples
    ).fit_predict(coordinates)
    if config.terminal_max_span_m is None:
        return initial

    labels = np.full(len(initial), -1, dtype="int64")
    next_label = 0
    for initial_label in np.unique(initial):
        indices = np.flatnonzero(initial == initial_label)
        if initial_label == -1:
            continue
        if len(indices) == 1:
            labels[indices] = next_label
            next_label += 1
            continue
        split = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=config.terminal_max_span_m,
            linkage="complete",
            metric="euclidean",
        ).fit_predict(coordinates[indices])
        for split_label in np.unique(split):
            labels[indices[split == split_label]] = next_label
            next_label += 1
    return labels


def resolve_terminal_rectangle_overlaps(terminals: pd.DataFrame) -> pd.DataFrame:
    """沿相邻码头 AIS 中心的主方向切开重叠矩形，且保持每个范围为矩形。"""
    if terminals.empty:
        return terminals.copy()
    rectangles = list(
        gpd.GeoSeries.from_wkt(terminals["polygon"], crs="EPSG:4326").to_crs("EPSG:3857")
    )
    centers = _project_coordinates(terminals)
    dwell = pd.to_numeric(terminals["dwell_minutes"], errors="coerce").fillna(0).to_numpy()
    terminal_ids = terminals["terminal_id"].to_numpy()

    # 只会缩小矩形，因此切分不会产生新的重叠；保留循环是为了处理同一矩形
    # 与多个邻居连续相交的情形。
    for _ in range(len(rectangles)):
        changed = False
        spatial_index = gpd.GeoSeries(rectangles, crs="EPSG:3857").sindex
        for left_index, left in enumerate(rectangles):
            for right_index in spatial_index.query(left, predicate="intersects"):
                if right_index <= left_index:
                    continue
                right = rectangles[right_index]
                overlap = left.intersection(right)
                if overlap.is_empty or overlap.area <= 1.0:
                    continue
                left_bounds, right_bounds = left.bounds, right.bounds
                delta_x = centers[left_index, 0] - centers[right_index, 0]
                delta_y = centers[left_index, 1] - centers[right_index, 1]
                # 以中心更分离的轴切开。中心重合时，时长更高（再按 ID）的一侧优先。
                if abs(delta_x) >= abs(delta_y):
                    cut = (max(left_bounds[0], right_bounds[0]) + min(left_bounds[2], right_bounds[2])) / 2
                    left_first = delta_x < 0 or (
                        delta_x == 0
                        and (dwell[left_index], -terminal_ids[left_index])
                        >= (dwell[right_index], -terminal_ids[right_index])
                    )
                    if left_first:
                        rectangles[left_index] = box(left_bounds[0], left_bounds[1], min(left_bounds[2], cut), left_bounds[3])
                        rectangles[right_index] = box(max(right_bounds[0], cut), right_bounds[1], right_bounds[2], right_bounds[3])
                    else:
                        rectangles[right_index] = box(right_bounds[0], right_bounds[1], min(right_bounds[2], cut), right_bounds[3])
                        rectangles[left_index] = box(max(left_bounds[0], cut), left_bounds[1], left_bounds[2], left_bounds[3])
                else:
                    cut = (max(left_bounds[1], right_bounds[1]) + min(left_bounds[3], right_bounds[3])) / 2
                    left_first = delta_y < 0 or (
                        delta_y == 0
                        and (dwell[left_index], -terminal_ids[left_index])
                        >= (dwell[right_index], -terminal_ids[right_index])
                    )
                    if left_first:
                        rectangles[left_index] = box(left_bounds[0], left_bounds[1], left_bounds[2], min(left_bounds[3], cut))
                        rectangles[right_index] = box(right_bounds[0], max(right_bounds[1], cut), right_bounds[2], right_bounds[3])
                    else:
                        rectangles[right_index] = box(right_bounds[0], right_bounds[1], right_bounds[2], min(right_bounds[3], cut))
                        rectangles[left_index] = box(left_bounds[0], max(left_bounds[1], cut), left_bounds[2], left_bounds[3])
                changed = True
        if not changed:
            break

    result = terminals.copy()
    result["polygon"] = gpd.GeoSeries(rectangles, crs="EPSG:3857").to_crs("EPSG:4326").to_wkt().to_numpy()
    return result


def build_terminals(berths: pd.DataFrame, config: PipelineConfig) -> pd.DataFrame:
    if berths.empty:
        return pd.DataFrame(columns=["terminal_id", "lat", "lon", "berth_count", "polygon"])
    geometries = gpd.GeoDataFrame(
        berths, geometry=gpd.GeoSeries.from_wkt(berths["polygon"]), crs="EPSG:4326"
    ).to_crs("EPSG:3857")
    # 使用泊位的 AIS 活动中心聚类，而不是矩形范围的几何质心。
    coords = _project_coordinates(geometries)
    geometries["terminal_id"] = terminal_cluster_labels(coords, config)

    records = []
    for terminal_id, group in geometries.loc[geometries["terminal_id"].ne(-1)].groupby("terminal_id", sort=True):
        merged = unary_union(group.geometry)
        try:
            outline = _regularize_geometry(
                merged, config.terminal_merge_buffer_m, config.terminal_simplify_m
            )
        except TopologicalError:
            outline = merged.envelope
        if config.terminal_shape_method == "bounding_rectangle":
            # 矩形化只发生在归属与中心已确定之后，不影响聚类或 AIS 中心。
            outline = outline.envelope
        elif config.terminal_shape_method != "merged_outline":
            raise ValueError(f"未知码头范围方法：{config.terminal_shape_method!r}")
        if config.terminal_outline_buffer_m > 0:
            # 范围外扩只发生在码头归属已确定之后，不影响 DBSCAN 聚类或 AIS 中心。
            join_style = 2 if config.terminal_shape_method == "bounding_rectangle" else 1
            outline = outline.buffer(config.terminal_outline_buffer_m, join_style=join_style)
        if config.terminal_shape_method == "bounding_rectangle":
            # 外扩后重新取 envelope，确保是严格的四边矩形而非圆角面。
            outline = outline.envelope
        else:
            outline = outline.simplify(config.terminal_simplify_m, preserve_topology=True)
        outline_wgs84 = gpd.GeoSeries([outline], crs="EPSG:3857").to_crs("EPSG:4326").iloc[0]
        center_lon, center_lat = weighted_medoid_lon_lat(
            group.assign(duration_min=group["dwell_minutes"])
        )
        records.append(
            {
                "terminal_id": terminal_id,
                "lat": center_lat,
                "lon": center_lon,
                "berth_count": len(group),
                "dwell_minutes": group["dwell_minutes"].sum(),
                "center_method": "duration_weighted_berth_medoid",
                "polygon": outline_wgs84.wkt,
            }
        )
    terminals = pd.DataFrame(records)
    if (
        config.terminal_shape_method == "bounding_rectangle"
        and config.terminal_resolve_rectangle_overlaps
    ):
        terminals = resolve_terminal_rectangle_overlaps(terminals)
    return terminals


def filter_berths(berths: pd.DataFrame, config: PipelineConfig) -> pd.DataFrame:
    return berths.loc[
        berths["distance_to_coast"].le(config.berth_coast_max_m)
        | (
            berths["distance_to_coast"].gt(config.berth_coast_max_m)
            & berths["inside_china_land"]
        )
    ].reset_index(drop=True)


def filter_anchorages(anchorages: pd.DataFrame, config: PipelineConfig) -> pd.DataFrame:
    # 开阔水域模式下，锚地的中心可以靠近岸边，但范围面仍会在后续步骤中
    # 裁掉距陆地边界不足 `anchorage_coast_min_m` 的部分。这样可保留从港外
    # 向深海延伸的锚地，避免仅因 AIS 中心偏岸就整块误删。
    coast_min_m = 0.0 if config.anchorage_open_water_only else config.anchorage_coast_min_m
    keep = anchorages["distance_to_coast"].between(coast_min_m, config.anchorage_coast_max_m)
    if config.anchorage_exclude_land_overlap:
        keep &= ~anchorages["inside_china_land"]
    return anchorages.loc[keep].reset_index(drop=True)


def exclude_anchorages_from_land(anchorages: pd.DataFrame, clearance_m: float = 0.0) -> pd.DataFrame:
    """移除内陆锚地中心，并从其余锚地面中裁掉陆地与河岸内侧区域。"""
    if anchorages.empty:
        return anchorages.copy()
    land_exclusion = get_china_land_geometry().buffer(clearance_m)
    areas = gpd.GeoSeries.from_wkt(anchorages["polygon"], crs="EPSG:4326").to_crs("EPSG:3857")
    centers = gpd.GeoSeries(
        gpd.points_from_xy(anchorages["lon"], anchorages["lat"]), crs="EPSG:4326"
    ).to_crs("EPSG:3857")
    center_inside_land = centers.within(land_exclusion)
    overlaps_land = areas.intersects(land_exclusion)
    clipped_areas = areas.difference(land_exclusion)
    keep = ~center_inside_land & ~clipped_areas.is_empty
    result = anchorages.loc[keep].copy().reset_index(drop=True)
    result_areas = gpd.GeoSeries(clipped_areas.loc[keep], crs="EPSG:3857").to_crs("EPSG:4326")
    result["polygon"] = result_areas.to_wkt().to_numpy()
    result["land_overlap_action"] = np.where(
        overlaps_land.loc[keep].to_numpy(), "land_area_clipped", "unchanged"
    )
    return result


def exclude_anchorages_from_terminals(
    anchorages: pd.DataFrame, terminals: pd.DataFrame, clearance_m: float = 0.0
) -> pd.DataFrame:
    """用固定码头范围约束锚地：剔除中心入港的误识别，并裁掉边缘重叠。"""
    if anchorages.empty or terminals.empty:
        return anchorages.copy()

    terminal_areas = gpd.GeoSeries.from_wkt(terminals["polygon"], crs="EPSG:4326").to_crs("EPSG:3857")
    terminal_union = terminal_areas.union_all().buffer(clearance_m)
    anchorage_areas = gpd.GeoSeries.from_wkt(anchorages["polygon"], crs="EPSG:4326").to_crs("EPSG:3857")
    anchorage_centers = gpd.GeoSeries(
        gpd.points_from_xy(anchorages["lon"], anchorages["lat"]), crs="EPSG:4326"
    ).to_crs("EPSG:3857")

    center_inside_terminal = anchorage_centers.within(terminal_union)
    overlaps_terminal = anchorage_areas.intersects(terminal_union)
    clipped_areas = anchorage_areas.difference(terminal_union)
    keep = ~center_inside_terminal & ~clipped_areas.is_empty
    result = anchorages.loc[keep].copy().reset_index(drop=True)
    result_areas = gpd.GeoSeries(clipped_areas.loc[keep], crs="EPSG:3857").to_crs("EPSG:4326")
    result["polygon"] = result_areas.to_wkt().to_numpy()
    result["terminal_overlap_action"] = np.where(
        overlaps_terminal.loc[keep].to_numpy(), "terminal_area_clipped", "unchanged"
    )
    return result


def _cache_path(config: PipelineConfig) -> Path:
    return RESULTS_DIR / "cache" / (
        f"stops_china_speed-{config.stop_speed_kn:g}_min-{config.min_stop_minutes}.pkl"
    )


def load_or_detect_stops(config: PipelineConfig, refresh_cache: bool) -> pd.DataFrame:
    cache_path = _cache_path(config)
    if cache_path.exists() and not refresh_cache:
        print(f"复用停泊段缓存：{cache_path}")
        return pd.read_pickle(cache_path)

    stops = detect_stops(prepare_ship_data(load_ais_data(config)), config)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    stops.to_pickle(cache_path)
    print(f"已保存停泊段缓存：{cache_path}")
    return stops


def export_results(
    berths: pd.DataFrame, anchorages: pd.DataFrame, terminals: pd.DataFrame, output_dir: Path
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    berths.to_csv(output_dir / "china_berths.csv", index=False)
    anchorages.to_csv(output_dir / "china_anchorages.csv", index=False)
    terminals.to_csv(output_dir / "china_terminals.csv", index=False)


def run_pipeline(
    config: PipelineConfig,
    output_dir: Optional[Path] = None,
    refresh_cache: bool = False,
) -> dict[str, int]:
    if output_dir is None:
        output_dir = next_result_dir()
    coastline = get_china_coastline_line()
    stops = classify_behavior(load_or_detect_stops(config, refresh_cache), config)

    berths = cluster_to_rectangles(
        run_dbscan(
            stops.loc[stops["behavior"].eq("berth_like")],
            config.berth_eps_m,
            config.berth_min_samples,
        ),
        config,
    )
    anchorages = cluster_to_anchorage_areas(
        run_anchorage_clustering(stops.loc[stops["behavior"].eq("anchorage_like")], config),
        config,
    )

    berths = filter_berths(add_land_flag(add_coast_distance(berths, coastline)), config)
    terminals = build_terminals(berths, config)
    # 码头展示形状（例如矩形）不得反向影响锚地识别。锚地排除始终使用同一
    # 聚类结果的原始合并轮廓，确保仅改变码头可视化范围面时锚地结果保持稳定。
    terminal_exclusion_areas = (
        build_terminals(berths, replace(config, terminal_shape_method="merged_outline"))
        if config.terminal_shape_method != "merged_outline"
        else terminals
    )
    anchorage_distance_reference = (
        get_china_land_boundary()
        if config.anchorage_use_land_boundary_distance
        else coastline
    )
    anchorages = add_land_flag(add_coast_distance(anchorages, anchorage_distance_reference))
    anchorages = filter_anchorages(anchorages, config)
    if config.anchorage_exclude_land_overlap:
        land_clearance = config.anchorage_land_clearance_m
        if config.anchorage_open_water_only:
            # 复用既有“距岸至少 3 km”规则到整个范围面，不能只检查中心。
            land_clearance = max(land_clearance, config.anchorage_coast_min_m)
        anchorages = exclude_anchorages_from_land(anchorages, land_clearance)
    if config.anchorage_exclude_terminal_overlap:
        anchorages = exclude_anchorages_from_terminals(
            anchorages, terminal_exclusion_areas, config.anchorage_terminal_clearance_m
        )
    export_results(berths, anchorages, terminals, output_dir)

    summary = {"berths": len(berths), "anchorages": len(anchorages), "terminals": len(terminals)}
    print(f"完成：泊位 {summary['berths']}，锚地 {summary['anchorages']}，码头 {summary['terminals']}")
    print(f"结果目录：{output_dir}")
    return summary
