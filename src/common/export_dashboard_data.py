"""将聚类结果与真实对照数据导出为地图看板使用的 GeoJSON。"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd
import geopandas as gpd
from shapely import from_wkt
from shapely.geometry import mapping

try:
    from .paths import (
        CHINA_SHP,
        COASTLINE_SHP,
        ITERATION_RESULTS_DIR,
        PROJECT_ROOT,
        REFERENCE_DIR,
        latest_result_dir,
    )
except ImportError:  # 支持 `python src/common/export_dashboard_data.py`
    from paths import (
        CHINA_SHP,
        COASTLINE_SHP,
        ITERATION_RESULTS_DIR,
        PROJECT_ROOT,
        REFERENCE_DIR,
        latest_result_dir,
    )


DASHBOARD_ROOT = PROJECT_ROOT / "dashboard"
PROCESSED_REFERENCE_ANCHORAGES = REFERENCE_DIR / "processed" / "中国锚地_去重.csv"


def _value(value):
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _feature_collection(frame: pd.DataFrame, geometry_column: str, property_columns: Iterable[str]) -> dict:
    features = []
    for _, row in frame.iterrows():
        try:
            geometry = from_wkt(row[geometry_column])
        except Exception:
            continue
        if geometry.is_empty:
            continue
        properties = {column: _value(row[column]) for column in property_columns if column in row}
        features.append({"type": "Feature", "geometry": mapping(geometry), "properties": properties})
    return {"type": "FeatureCollection", "features": features}


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"缺少看板输入文件：{path}")
    return pd.read_csv(path, encoding="utf-8-sig")


def _read_terminals(result_dir: Path) -> pd.DataFrame:
    """优先读取现行码头文件，并兼容改名前的历史结果。"""
    terminal_path = result_dir / "china_terminals.csv"
    if terminal_path.exists():
        return _read_csv(terminal_path)

    legacy_port_path = result_dir / "china_ports.csv"
    terminals = _read_csv(legacy_port_path)
    return terminals.rename(columns={"port_id": "terminal_id"})


def _write_json(data_dir: Path, filename: str, content: dict) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / filename).write_text(
        json.dumps(content, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )


def _write_standalone_data(dashboard_dir: Path, content: dict) -> None:
    """写入本地脚本，使 index.html 在 file:// 模式下也能加载数据。"""
    serialized = json.dumps(content, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    dashboard_dir.mkdir(parents=True, exist_ok=True)
    (dashboard_dir / "data.js").write_text(
        f"window.DASHBOARD_DATA = {serialized};\n", encoding="utf-8"
    )


def _dashboard_dir_for_result(result_dir: Path) -> Path:
    """参数迭代结果使用同名独立看板；普通编号结果继续使用根看板。"""
    try:
        relative = result_dir.resolve().relative_to(ITERATION_RESULTS_DIR.resolve())
    except ValueError:
        return DASHBOARD_ROOT
    if len(relative.parts) == 1:
        return DASHBOARD_ROOT / "iterations" / relative.name
    return DASHBOARD_ROOT


def _write_iteration_index(dashboard_dir: Path) -> None:
    """为迭代看板生成入口页，复用根看板的样式与交互脚本。"""
    source = (DASHBOARD_ROOT / "index.html").read_text(encoding="utf-8")
    content = source.replace('href="styles.css"', 'href="../../styles.css"').replace(
        'src="app.js"', 'src="../../app.js"'
    )
    (dashboard_dir / "index.html").write_text(content, encoding="utf-8")


def _local_base_layers() -> tuple[dict, dict]:
    """导出本地中国陆地与海岸线，网络底图不可用时仍能判断空间位置。"""
    countries = gpd.read_file(CHINA_SHP)
    china = countries.loc[countries["NAME"].isin(["China", "Taiwan"])].to_crs("EPSG:4326")
    coastlines = gpd.read_file(COASTLINE_SHP).to_crs("EPSG:4326")
    china_shape = china.unary_union
    china_coast = coastlines.loc[coastlines.intersects(china_shape)]
    land = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "geometry": mapping(china_shape), "properties": {"name": "中国陆地区域"}}],
    }
    coast = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": mapping(geometry), "properties": {}}
            for geometry in china_coast.geometry
            if geometry is not None and not geometry.is_empty
        ],
    }
    return land, coast


def export_dashboard_data(result_dir: Path | None = None) -> dict[str, int | str]:
    result_dir = result_dir or latest_result_dir()
    dashboard_dir = _dashboard_dir_for_result(result_dir)
    data_dir = dashboard_dir / "data"
    berths = _read_csv(result_dir / "china_berths.csv")
    anchorages = _read_csv(result_dir / "china_anchorages.csv")
    terminals = _read_terminals(result_dir)

    china_reference_dir = REFERENCE_DIR / "实际数据中国版"
    reference_dir = china_reference_dir if china_reference_dir.exists() else REFERENCE_DIR
    reference_berths = _read_csv(reference_dir / "码头.csv")
    reference_anchorages = _read_csv(
        PROCESSED_REFERENCE_ANCHORAGES
        if PROCESSED_REFERENCE_ANCHORAGES.exists()
        else reference_dir / "锚地.csv"
    )
    china_land, china_coast = _local_base_layers()

    berth_features = _feature_collection(
        berths,
        "polygon",
        [
            "cluster_id",
            "lat",
            "lon",
            "count",
            "dwell_minutes",
            "center_method",
            "type",
            "distance_to_coast",
            "inside_china_land",
        ],
    )
    anchorage_features = _feature_collection(
        anchorages,
        "polygon",
        [
            "cluster_id",
            "lat",
            "lon",
            "count",
            "dwell_minutes",
            "center_method",
            "radius_m",
            "type",
            "distance_to_coast",
            "inside_china_land",
            "land_overlap_action",
            "terminal_overlap_action",
        ],
    )
    terminal_features = _feature_collection(
        terminals,
        "polygon",
        ["terminal_id", "lat", "lon", "berth_count", "dwell_minutes", "center_method"],
    )
    reference_berth_features = _feature_collection(reference_berths, "geom", ["pid", "name", "guid"])
    reference_anchorage_features = _feature_collection(reference_anchorages, "geom", ["pid", "name", "guid"])

    _write_json(data_dir, "berths.geojson", berth_features)
    _write_json(data_dir, "anchorages.geojson", anchorage_features)
    _write_json(data_dir, "terminals.geojson", terminal_features)
    _write_json(data_dir, "reference_berths.geojson", reference_berth_features)
    _write_json(data_dir, "reference_anchorages.geojson", reference_anchorage_features)
    _write_json(data_dir, "china_land.geojson", china_land)
    _write_json(data_dir, "china_coast.geojson", china_coast)

    summary = {
        "result_version": result_dir.name,
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "predicted_berths": len(berths),
        "predicted_anchorages": len(anchorages),
        "predicted_terminals": len(terminals),
        "reference_berths": len(reference_berths),
        "reference_anchorages": len(reference_anchorages),
        "dashboard_path": str(dashboard_dir.relative_to(PROJECT_ROOT)),
    }
    _write_json(data_dir, "summary.json", summary)
    _write_standalone_data(
        dashboard_dir,
        {
            "summary": summary,
            "berths": berth_features,
            "anchorages": anchorage_features,
            "terminals": terminal_features,
            "referenceBerths": reference_berth_features,
            "referenceAnchorages": reference_anchorage_features,
            "chinaLand": china_land,
            "chinaCoast": china_coast,
        }
    )
    if dashboard_dir != DASHBOARD_ROOT:
        _write_iteration_index(dashboard_dir)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="导出指定结果目录的地图看板数据")
    parser.add_argument("--result-dir", type=Path, default=None, help="结果目录；默认使用最大编号目录")
    args = parser.parse_args()
    summary = export_dashboard_data(args.result_dir)
    print("地图数据已导出：", summary)
