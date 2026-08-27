"""生成无重叠的中国真实锚地参考数据。"""
from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.ops import unary_union

try:
    from .paths import REFERENCE_DIR
except ImportError:  # pragma: no cover
    from paths import REFERENCE_DIR


CHINA_REFERENCE_DIR = REFERENCE_DIR / "实际数据中国版"
DEFAULT_SOURCE = CHINA_REFERENCE_DIR / "锚地.csv"
PROCESSED_REFERENCE_DIR = REFERENCE_DIR / "processed"
DEFAULT_OUTPUT = PROCESSED_REFERENCE_DIR / "中国锚地_去重.csv"
DEFAULT_AUDIT_OUTPUT = PROCESSED_REFERENCE_DIR / "中国锚地_去重记录.csv"
FULL_COVERAGE_THRESHOLD = 0.95


def deduplicate_anchorages(
    frame: pd.DataFrame, full_coverage_threshold: float = FULL_COVERAGE_THRESHOLD
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """按面积优先级去重，并裁掉较小面与已保留面的重叠区域。

    输入先按面积降序、pid 升序处理：被单一更大面覆盖阈值以上的记录直接删除；
    其余记录保留未重叠的剩余部分。这样既不会把相邻真实锚地粗暴合并，也能保证
    导出的参考范围面之间没有面积重叠。
    """
    if not 0 < full_coverage_threshold <= 1:
        raise ValueError("完全覆盖阈值必须在 (0, 1] 内")
    required = {"pid", "name", "geom"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"真实锚地缺少字段：{sorted(missing)}")

    geometry = gpd.GeoSeries.from_wkt(frame["geom"], crs="EPSG:4326").to_crs("EPSG:3857")
    if geometry.is_empty.any() or (~geometry.is_valid).any():
        raise ValueError("真实锚地包含空或无效几何，无法安全去重")
    records = frame.copy()
    records["_geometry"] = geometry
    records["_area_m2"] = geometry.area
    ordered = records.sort_values(["_area_m2", "pid"], ascending=[False, True], kind="stable")

    kept_rows: list[dict[str, object]] = []
    kept_geometries = []
    audit_rows: list[dict[str, object]] = []
    for index, row in ordered.iterrows():
        geometry = row["_geometry"]
        duplicate_of = None
        for kept_row, kept_geometry in zip(kept_rows, kept_geometries):
            if not geometry.intersects(kept_geometry):
                continue
            coverage = geometry.intersection(kept_geometry).area / row["_area_m2"]
            if coverage >= full_coverage_threshold:
                duplicate_of = (kept_row, float(coverage))
                break
        if duplicate_of is not None:
            kept, coverage = duplicate_of
            audit_rows.append(
                {
                    "action": "dropped_near_fully_covered",
                    "source_pid": row["pid"],
                    "source_name": row["name"],
                    "source_area_km2": row["_area_m2"] / 1_000_000,
                    "retained_pid": kept["pid"],
                    "retained_name": kept["name"],
                    "overlap_area_km2": geometry.intersection(kept["_geometry"]).area / 1_000_000,
                    "source_area_coverage": coverage,
                    "rule": f"single_larger_coverage>={full_coverage_threshold:.3f}",
                }
            )
            continue

        occupied = unary_union(kept_geometries) if kept_geometries else None
        resolved = geometry if occupied is None else geometry.difference(occupied)
        if resolved.is_empty or resolved.area == 0:
            audit_rows.append(
                {
                    "action": "dropped_fully_covered_by_multiple",
                    "source_pid": row["pid"],
                    "source_name": row["name"],
                    "source_area_km2": row["_area_m2"] / 1_000_000,
                    "retained_pid": None,
                    "retained_name": None,
                    "overlap_area_km2": row["_area_m2"] / 1_000_000,
                    "source_area_coverage": 1.0,
                    "rule": "remaining_area=0",
                }
            )
            continue

        remaining_fraction = resolved.area / row["_area_m2"]
        if remaining_fraction < 1:
            audit_rows.append(
                {
                    "action": "partial_overlap_clipped",
                    "source_pid": row["pid"],
                    "source_name": row["name"],
                    "source_area_km2": row["_area_m2"] / 1_000_000,
                    "retained_pid": None,
                    "retained_name": None,
                    "overlap_area_km2": (row["_area_m2"] - resolved.area) / 1_000_000,
                    "source_area_coverage": 1 - remaining_fraction,
                    "rule": "clip_against_larger_retained_areas",
                }
            )
        retained = row.drop(labels=["_geometry", "_area_m2"]).to_dict()
        resolved_wgs84 = gpd.GeoSeries([resolved], crs="EPSG:3857").to_crs("EPSG:4326").iloc[0]
        retained["geom"] = resolved_wgs84.wkt
        if "point" in retained:
            retained["point"] = resolved_wgs84.representative_point().wkt
        retained["_geometry"] = resolved
        kept_rows.append(retained)
        kept_geometries.append(resolved)

    result = pd.DataFrame(kept_rows).drop(columns="_geometry").sort_values(
        "pid", kind="stable"
    ).reset_index(drop=True)
    audit = pd.DataFrame(audit_rows)
    return result, audit


def main() -> None:
    parser = argparse.ArgumentParser(description="去重真实锚地：完整覆盖时保留面积最大的记录")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--audit-output", type=Path, default=DEFAULT_AUDIT_OUTPUT)
    parser.add_argument("--threshold", type=float, default=FULL_COVERAGE_THRESHOLD)
    args = parser.parse_args()

    source = pd.read_csv(args.source, encoding="utf-8-sig")
    result, audit = deduplicate_anchorages(source, args.threshold)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.audit_output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False, encoding="utf-8-sig")
    audit.to_csv(args.audit_output, index=False, encoding="utf-8-sig")
    dropped = int(audit["action"].str.startswith("dropped_").sum()) if not audit.empty else 0
    clipped = int(audit["action"].eq("partial_overlap_clipped").sum()) if not audit.empty else 0
    print(
        f"真实锚地处理完成：{len(source)} → {len(result)}；"
        f"删除 {dropped} 条、裁切 {clipped} 条重叠面；输出：{args.output}"
    )


if __name__ == "__main__":
    main()
