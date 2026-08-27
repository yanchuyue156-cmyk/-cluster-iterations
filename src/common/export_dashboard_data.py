"""将聚类结果与真实对照数据导出为地图看板使用的 GeoJSON。"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import shutil
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
        CURRENT_ITERATION_NAME,
        ITERATION_RESULTS_DIR,
        PROJECT_ROOT,
        REFERENCE_DIR,
        current_iteration_result_dir,
    )
except ImportError:  # 支持 `python src/common/export_dashboard_data.py`
    from paths import (
        CHINA_SHP,
        COASTLINE_SHP,
        CURRENT_ITERATION_NAME,
        ITERATION_RESULTS_DIR,
        PROJECT_ROOT,
        REFERENCE_DIR,
        current_iteration_result_dir,
    )


DASHBOARD_ROOT = PROJECT_ROOT / "dashboard"
SHARED_DATA_DIR = DASHBOARD_ROOT / "shared"
MAP_TEMPLATE = DASHBOARD_ROOT / "map.html"
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


def _reference_anchorages_path(result_dir: Path, reference_dir: Path) -> Path:
    """保持历史看板的真实锚地口径：第 09 轮起才改用去重版本。"""
    try:
        iteration_number = int(result_dir.name.split("_", 2)[1])
    except (IndexError, ValueError):
        iteration_number = 9
    if iteration_number < 9:
        return reference_dir / "锚地.csv"
    if PROCESSED_REFERENCE_ANCHORAGES.exists():
        return PROCESSED_REFERENCE_ANCHORAGES
    return reference_dir / "锚地.csv"


def _serialize_javascript(content: dict) -> str:
    return json.dumps(content, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def _write_shared_base_data(content: dict) -> str:
    """将公共底图和参考图层只保存一次，返回其稳定文件名。"""
    serialized = _serialize_javascript(content)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:12]
    filename = f"base-{digest}.js"
    SHARED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = SHARED_DATA_DIR / filename
    if not path.exists():
        path.write_text(f"window.DASHBOARD_SHARED_DATA = {serialized};\n", encoding="utf-8")
    return filename


def _write_standalone_data(dashboard_dir: Path, content: dict) -> None:
    """写入本轮专属数据；公共图层由 shared/base-*.js 预先加载。"""
    serialized = json.dumps(content, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    dashboard_dir.mkdir(parents=True, exist_ok=True)
    (dashboard_dir / "data.js").write_text(
        f"window.DASHBOARD_DATA = {{...window.DASHBOARD_SHARED_DATA,...{serialized}}};\n",
        encoding="utf-8",
    )


def _dashboard_dir_for_result(result_dir: Path) -> Path:
    """参数迭代结果使用同名看板；非迭代结果隔离到 history 下。"""
    try:
        relative = result_dir.resolve().relative_to(ITERATION_RESULTS_DIR.resolve())
    except ValueError:
        return DASHBOARD_ROOT
    if len(relative.parts) == 1:
        return DASHBOARD_ROOT / "iterations" / relative.name
    return DASHBOARD_ROOT / "history" / result_dir.name


def _write_iteration_index(dashboard_dir: Path, shared_filename: str) -> None:
    """为迭代看板生成入口页，复用根看板的样式与交互脚本。"""
    source = MAP_TEMPLATE.read_text(encoding="utf-8")
    content = source.replace('href="styles.css"', 'href="../../styles.css"').replace(
        'src="app.js"', 'src="../../app.js"'
    )
    content = content.replace("{{SHARED_DATA}}", f"../../shared/{shared_filename}")
    (dashboard_dir / "index.html").write_text(content, encoding="utf-8")


def _iteration_description(iteration_name: str) -> str:
    try:
        module = importlib.import_module(f"src.iterations.{iteration_name}")
        return str(getattr(module, "DESCRIPTION", ""))
    except Exception:
        return ""


def _write_dashboard_catalog() -> None:
    """重建可直接双击打开的看板目录页数据。"""
    items = []
    for dashboard_dir in sorted((DASHBOARD_ROOT / "iterations").glob("iteration_*")):
        summary_path = dashboard_dir / "summary.json"
        if not summary_path.exists():
            continue
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        name = dashboard_dir.name
        items.append(
            {
                "name": name,
                "description": _iteration_description(name),
                "href": f"iterations/{name}/index.html",
                "isCurrent": name == CURRENT_ITERATION_NAME,
                **summary,
            }
        )
    serialized = _serialize_javascript({"current": CURRENT_ITERATION_NAME, "items": items})
    (DASHBOARD_ROOT / "catalog.js").write_text(
        f"window.DASHBOARD_CATALOG = {serialized};\n", encoding="utf-8"
    )


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
    result_dir = result_dir or current_iteration_result_dir()
    dashboard_dir = _dashboard_dir_for_result(result_dir)
    berths = _read_csv(result_dir / "china_berths.csv")
    anchorages = _read_csv(result_dir / "china_anchorages.csv")
    terminals = _read_terminals(result_dir)

    china_reference_dir = REFERENCE_DIR / "实际数据中国版"
    reference_dir = china_reference_dir if china_reference_dir.exists() else REFERENCE_DIR
    reference_berths = _read_csv(reference_dir / "码头.csv")
    reference_anchorages = _read_csv(_reference_anchorages_path(result_dir, reference_dir))
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
    dashboard_dir.mkdir(parents=True, exist_ok=True)
    (dashboard_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    shared_filename = _write_shared_base_data(
        {
            "referenceBerths": reference_berth_features,
            "referenceAnchorages": reference_anchorage_features,
            "chinaLand": china_land,
            "chinaCoast": china_coast,
        }
    )
    _write_standalone_data(
        dashboard_dir,
        {
            "summary": summary,
            "berths": berth_features,
            "anchorages": anchorage_features,
            "terminals": terminal_features,
        }
    )
    _write_iteration_index(dashboard_dir, shared_filename)
    stale_data_dir = dashboard_dir / "data"
    if stale_data_dir.exists():
        shutil.rmtree(stale_data_dir)
    _write_dashboard_catalog()
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="导出指定结果目录的地图看板数据")
    parser.add_argument("--result-dir", type=Path, default=None, help="结果目录；默认使用当前参数迭代")
    args = parser.parse_args()
    summary = export_dashboard_data(args.result_dir)
    print("地图数据已导出：", summary)
