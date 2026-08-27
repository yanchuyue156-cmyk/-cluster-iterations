from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from pathlib import Path

import pandas as pd
from paths import AIS_DATA_DIR, PROJECT_ROOT, RESULTS_DIR

USE_COLS = ["MMSI", "BaseDateTime", "Latitude", "Longitude"]
DTYPE_MAP = {
    "MMSI": "int64",
    "Latitude": "float64",
    "Longitude": "float64",
}

def read_ship_csv(path):
    last_error = None
    for encoding in ("utf-8", "gbk", "latin1"):
        try:
            return pd.read_csv(
                path,
                usecols=USE_COLS,
                dtype=DTYPE_MAP,
                encoding=encoding,
                low_memory=False,
                memory_map=True,
            )
        except UnicodeDecodeError as exc:
            last_error = exc

    if last_error is not None:
        raise last_error
    raise RuntimeError(f"❌ 读取失败: {path}")

def load_all_ships_data():
    print("🚢 开始读取数据", flush=True)

    folder_path = AIS_DATA_DIR
    print("📁 数据路径:", folder_path, flush=True)

    if not folder_path.exists():
        raise FileNotFoundError(f"❌ 找不到文件夹: {folder_path}")

    all_files = sorted(p.name for p in folder_path.glob("*.csv"))
    if len(all_files) == 0:
        raise ValueError("❌ cleaned 文件夹中没有 CSV 文件")

    print(f"📊 共发现 {len(all_files)} 个 CSV 文件", flush=True)

    df_list = []
    max_workers = min(8, len(all_files), os.cpu_count() or 1)
    print(f"⚙️ 并发读取线程数: {max_workers}", flush=True)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {
            executor.submit(read_ship_csv, folder_path / file): file for file in all_files
        }
        for i, future in enumerate(as_completed(future_to_file), 1):
            file = future_to_file[future]
            temp = future.result()
            df_list.append(temp)
            print(f"✔ [{i}/{len(all_files)}] 已读取: {file} -> {temp.shape}", flush=True)

    df = pd.concat(df_list, ignore_index=True)

    print("\n✅ 读取完成", flush=True)
    print("📦 总数据量:", len(df), flush=True)
    print("📐 数据维度:", df.shape, flush=True)
    
    return df

# -----------------------------------------------------------------------------
# 下面是你之前的聚类 + 绘图 + 输出逻辑（已整合中国数量打印）
# -----------------------------------------------------------------------------
from pathlib import Path
import contextily as ctx
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
from sklearn.cluster import DBSCAN
import utm

BASE_DIR = PROJECT_ROOT
LEGACY_RESULTS_DIR = RESULTS_DIR / "legacy-basic"

def print_progress(step, total, label):
    width = 28
    filled = int(width * step / total)
    bar = "#" * filled + "-" * (width - filled)
    percent = int(100 * step / total)
    print(f"[{bar}] {percent:>3}% {label}", flush=True)

def haversine(lat1, lon1, lat2, lon2):
    earth_radius = 6371000
    lat1 = np.radians(lat1)
    lon1 = np.radians(lon1)
    lat2 = np.radians(lat2)
    lon2 = np.radians(lon2)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * earth_radius * np.arctan2(np.sqrt(a), np.sqrt(1 - a))

def to_utm(lat, lon):
    return utm.from_latlon(lat, lon)[:2]

def filter_china(df):
    return df[
        (df["lat"] >= 18.0) & (df["lat"] <= 54.0) &
        (df["lon"] >= 73.0) & (df["lon"] <= 135.0)
    ].copy()

def prepare_ship_data(df):
    df = df.copy()
    df.columns = df.columns.str.strip()
    df = df.rename(
        columns={"BaseDateTime": "timestamp", "Latitude": "lat", "Longitude": "lon"}
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values(["MMSI", "timestamp"]).reset_index(drop=True)
    print("数据量:", len(df), flush=True)
    return df

def detect_stops(df, stop_speed_kn=1, min_stop_minutes=60):
    gb = df.groupby("MMSI")
    df["lat_prev"] = gb["lat"].shift(1)
    df["lon_prev"] = gb["lon"].shift(1)
    df["time_prev"] = gb["timestamp"].shift(1)
    df["time_diff"] = (df["timestamp"] - df["time_prev"]).dt.total_seconds()
    df["distance"] = haversine(df["lat"], df["lon"], df["lat_prev"], df["lon_prev"])
    df["speed_kn"] = (df["distance"] / df["time_diff"]) * 1.94384
    df["speed_kn"] = df["speed_kn"].replace([np.inf, -np.inf], 0).fillna(0)
    df["stop"] = (df["speed_kn"] < stop_speed_kn).astype(int)
    df["stop_group"] = gb["stop"].transform(lambda x: (x != x.shift(1)).cumsum())

    stops = (
        df[df["stop"] == 1]
        .groupby(["MMSI", "stop_group"])
        .agg(lat=("lat", "mean"), lon=("lon", "mean"), start=("timestamp", "min"), end=("timestamp", "max"))
    )
    stops["duration"] = (stops["end"] - stops["start"]).dt.total_seconds() / 60
    stops = stops[stops["duration"] >= min_stop_minutes].reset_index()
    print("有效停泊点:", len(stops), flush=True)
    return stops

def cluster_ports(stops, berth_eps=100, berth_min_samples=3, port_eps=8000, port_min_samples=10):
    if stops.empty:
        raise ValueError("❌ 没有满足条件的停泊点")

    stops = stops.copy()
    stops[["x", "y"]] = stops.apply(lambda row: pd.Series(to_utm(row.lat, row.lon)), axis=1)

    berth_db = DBSCAN(eps=berth_eps, min_samples=berth_min_samples)
    stops["cluster"] = berth_db.fit_predict(stops[["x", "y"]].values)

    berths = (
        stops[stops["cluster"] != -1]
        .groupby("cluster")
        .agg(lat=("lat", "mean"), lon=("lon", "mean"), count=("cluster", "count"))
        .reset_index()
    )
    if berths.empty:
        raise ValueError("❌ 无有效泊位")

    berths[["x", "y"]] = berths.apply(lambda r: pd.Series(to_utm(r.lat, r.lon)), axis=1)
    port_db = DBSCAN(eps=port_eps, min_samples=port_min_samples)
    berths["port_id"] = port_db.fit_predict(berths[["x", "y"]].values)

    ports = (
        berths[berths["port_id"] != -1]
        .groupby("port_id")
        .agg(lat=("lat", "mean"), lon=("lon", "mean"), count=("port_id", "count"))
        .reset_index()
    )
    if ports.empty:
        raise ValueError("❌ 无有效港口")

    print("\n====================")
    print("世界泊位数量:", len(berths))
    print("世界港口数量:", len(ports))
    print("====================")
    return berths, ports

def save_overview(berths, ports, filename, title):
    try:
        gdf_b = gpd.GeoDataFrame(berths, geometry=gpd.points_from_xy(berths.lon, berths.lat), crs="EPSG:4326").to_crs(epsg=3857)
        gdf_p = gpd.GeoDataFrame(ports, geometry=gpd.points_from_xy(ports.lon, ports.lat), crs="EPSG:4326").to_crs(epsg=3857)

        fig, ax = plt.subplots(figsize=(12, 10))
        gdf_b.plot(ax=ax, color="blue", markersize=20)
        gdf_p.plot(ax=ax, color="none", edgecolor="red", linewidth=2, markersize=100)
        ax.set_axis_off()
        plt.title(title)
        plt.savefig(LEGACY_RESULTS_DIR / filename, dpi=300, bbox_inches="tight")
        plt.close()
        print(f"✔ 已保存：{filename}")
    except Exception as e:
        print(f"⚠️ 绘图失败：{e}")

def save_outputs(berths, ports):
    LEGACY_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    # 世界
    berths.to_csv(LEGACY_RESULTS_DIR / "world_berths.csv", index=False, encoding="utf-8-sig")
    ports.to_csv(LEGACY_RESULTS_DIR / "world_ports.csv", index=False, encoding="utf-8-sig")
    save_overview(berths, ports, "world_overview.png", "World Berths & Ports")

    # 中国
    ch_berths = filter_china(berths)
    ch_ports = filter_china(ports)

    # ====================== 你要的输出就在这里！======================
    print("\n==================== 中国区域统计 ====================")
    print("中国最终泊位数量:", len(ch_berths))
    print("中国最终港口数量:", len(ch_ports))
    print("========================================================\n")

    ch_berths.to_csv(LEGACY_RESULTS_DIR / "china_berths.csv", index=False, encoding="utf-8-sig")
    ch_ports.to_csv(LEGACY_RESULTS_DIR / "china_ports.csv", index=False, encoding="utf-8-sig")
    save_overview(ch_berths, ch_ports, "china_overview.png", "China Berths & Ports")

    print("\n✅ 全部输出完成：世界+中国双版本")
    print("✅ 泊位=蓝色点 | 港口=红色空心圆")

def run():
    df = load_all_ships_data()
    prepared = prepare_ship_data(df)
    stops = detect_stops(prepared, min_stop_minutes=60)
    berths, ports = cluster_ports(stops)
    save_outputs(berths, ports)

if __name__ == "__main__":
    run()
