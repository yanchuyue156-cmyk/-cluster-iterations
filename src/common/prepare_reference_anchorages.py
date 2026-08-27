"""生成去重后的中国真实锚地参考数据，保留完全覆盖关系中面积最大的记录。"""
from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import pandas as pd

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
    """若一个锚地被已保留的更大锚地覆盖阈值以上，则删除它。

    输入先按面积降序、pid 升序处理，因此保留记录一定是面积更大者；面积相同的
    完全重合记录使用较小 pid 作为稳定的保留规则。
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

    kept_indices: list[int] = []
    audit_rows: list[dict[str, object]] = []
    for index, row in ordered.iterrows():
        duplicate_of = None
        for kept_index in kept_indices:
            kept = records.loc[kept_index]
            if not row["_geometry"].intersects(kept["_geometry"]):
                continue
            coverage = row["_geometry"].intersection(kept["_geometry"]).area / row["_area_m2"]
            if coverage >= full_coverage_threshold:
                duplicate_of = (kept, float(coverage))
                break
        if duplicate_of is None:
            kept_indices.append(index)
            continue
        kept, coverage = duplicate_of
        audit_rows.append(
            {
                "dropped_pid": row["pid"],
                "dropped_name": row["name"],
                "dropped_area_km2": row["_area_m2"] / 1_000_000,
                "retained_pid": kept["pid"],
                "retained_name": kept["name"],
                "retained_area_km2": kept["_area_m2"] / 1_000_000,
                "smaller_area_coverage": coverage,
                "rule": f"smaller_area_coverage>={full_coverage_threshold:.3f}",
            }
        )
    result = frame.loc[kept_indices].sort_values("pid", kind="stable").reset_index(drop=True)
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
    print(
        f"真实锚地去重完成：{len(source)} → {len(result)}；"
        f"删除 {len(audit)} 条；输出：{args.output}"
    )


if __name__ == "__main__":
    main()
