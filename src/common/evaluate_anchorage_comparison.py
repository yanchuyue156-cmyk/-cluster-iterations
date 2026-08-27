"""Evaluate one iteration's predicted anchorage areas against processed reference anchorages."""
from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
from shapely import from_wkt, make_valid

try:
    from .paths import REFERENCE_DIR
except ImportError:  # pragma: no cover
    from paths import REFERENCE_DIR


METRIC_CRS = "EPSG:3857"
DEFAULT_MATCH_RADIUS_M = 10_000.0
QUALIFYING_OVERLAP_MIN_M2 = 1.0
PROCESSED_REFERENCE_PATH = REFERENCE_DIR / "processed" / "中国锚地_去重.csv"


def _valid(geometry):
    return geometry if geometry.is_valid else make_valid(geometry)


def _load_reference() -> tuple[pd.DataFrame, gpd.GeoSeries, gpd.GeoSeries]:
    reference = pd.read_csv(PROCESSED_REFERENCE_PATH, encoding="utf-8-sig")
    points = gpd.GeoSeries.from_wkt(reference["point"], crs="EPSG:4326").to_crs(METRIC_CRS)
    polygons = gpd.GeoSeries.from_wkt(reference["geom"], crs="EPSG:4326").to_crs(METRIC_CRS)
    return reference, points, polygons.map(_valid)


def _load_predictions(result_dir: Path) -> tuple[pd.DataFrame, gpd.GeoSeries, gpd.GeoSeries]:
    predictions = pd.read_csv(result_dir / "china_anchorages.csv")
    points = gpd.GeoSeries(
        gpd.points_from_xy(predictions["lon"], predictions["lat"]), crs="EPSG:4326"
    ).to_crs(METRIC_CRS)
    polygons = gpd.GeoSeries.from_wkt(predictions["polygon"], crs="EPSG:4326").to_crs(METRIC_CRS)
    return predictions, points, polygons.map(_valid)


def _one_to_one_match(
    prediction_points: gpd.GeoSeries, reference_points: gpd.GeoSeries, radius_m: float
) -> list[tuple[int, int, float]]:
    """在中心距离阈值内选择总距离最小的一对一匹配。"""
    pred_xy = np.column_stack((prediction_points.x, prediction_points.y))
    ref_xy = np.column_stack((reference_points.x, reference_points.y))
    distances = np.hypot(pred_xy[:, None, 0] - ref_xy[None, :, 0], pred_xy[:, None, 1] - ref_xy[None, :, 1])
    unavailable = radius_m * 1000
    costs = np.full((len(pred_xy), len(ref_xy) + len(pred_xy)), unavailable, dtype="float64")
    costs[:, : len(ref_xy)] = np.where(distances <= radius_m, distances, unavailable)
    costs[:, len(ref_xy) :] = radius_m
    rows, columns = linear_sum_assignment(costs)
    return [
        (int(row), int(column), float(distances[row, column]))
        for row, column in zip(rows, columns)
        if column < len(ref_xy) and distances[row, column] <= radius_m
    ]


def _overlay_rows(
    prediction_polygons: gpd.GeoSeries, reference_polygons: gpd.GeoSeries
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    reference_index = reference_polygons.sindex
    prediction_index = prediction_polygons.sindex
    predicted_rows = []
    for index, geometry in prediction_polygons.items():
        candidates = reference_index.query(geometry, predicate="intersects")
        covered = reference_polygons.iloc[candidates].union_all() if len(candidates) else None
        intersection = geometry.intersection(covered).area if covered is not None else 0.0
        predicted_rows.append(
            {
                "prediction_index": index,
                "overlapping_reference_count": len(candidates),
                "predicted_area_m2": geometry.area,
                "overlap_area_m2": intersection,
                "predicted_area_precision": intersection / geometry.area if geometry.area else 0.0,
            }
        )
    reference_rows = []
    for index, geometry in reference_polygons.items():
        candidates = prediction_index.query(geometry, predicate="intersects")
        covered = prediction_polygons.iloc[candidates].union_all() if len(candidates) else None
        intersection = geometry.intersection(covered).area if covered is not None else 0.0
        reference_rows.append(
            {
                "reference_index": index,
                "overlapping_prediction_count": len(candidates),
                "reference_area_m2": geometry.area,
                "overlap_area_m2": intersection,
                "reference_area_recall": intersection / geometry.area if geometry.area else 0.0,
            }
        )
    prediction_union = prediction_polygons.union_all()
    reference_union = reference_polygons.union_all()
    intersection = prediction_union.intersection(reference_union).area
    union = prediction_union.union(reference_union).area
    totals = {
        "global_precision": intersection / prediction_union.area if prediction_union.area else 0.0,
        "global_recall": intersection / reference_union.area if reference_union.area else 0.0,
        "global_iou": intersection / union if union else 0.0,
    }
    return pd.DataFrame(predicted_rows), pd.DataFrame(reference_rows), totals


def _qualifying_relations(
    prediction_polygons: gpd.GeoSeries, reference_polygons: gpd.GeoSeries
) -> pd.DataFrame:
    reference_index = reference_polygons.sindex
    rows = []
    for prediction_index, prediction in prediction_polygons.items():
        for reference_index_value in reference_index.query(prediction, predicate="intersects"):
            reference = reference_polygons.iloc[reference_index_value]
            overlap = prediction.intersection(reference).area
            if overlap > QUALIFYING_OVERLAP_MIN_M2:
                rows.append(
                    {
                        "prediction_index": prediction_index,
                        "reference_index": int(reference_index_value),
                        "overlap_area_m2": overlap,
                    }
                )
    return pd.DataFrame(rows)


def evaluate(result_dir: Path, match_radius_m: float = DEFAULT_MATCH_RADIUS_M) -> dict[str, Path]:
    predictions, prediction_points, prediction_polygons = _load_predictions(result_dir)
    references, reference_points, reference_polygons = _load_reference()
    matches = _one_to_one_match(prediction_points, reference_points, match_radius_m)
    pairs = []
    for prediction_index, reference_index, distance_m in matches:
        prediction = prediction_polygons.iloc[prediction_index]
        reference = reference_polygons.iloc[reference_index]
        intersection = prediction.intersection(reference).area
        union = prediction.union(reference).area
        pairs.append(
            {
                "cluster_id": predictions.iloc[prediction_index]["cluster_id"],
                "reference_pid": references.iloc[reference_index]["pid"],
                "reference_name": references.iloc[reference_index]["name"],
                "center_distance_m": distance_m,
                "predicted_area_m2": prediction.area,
                "reference_area_m2": reference.area,
                "area_ratio_predicted_to_reference": prediction.area / reference.area,
                "intersection_area_m2": intersection,
                "iou": intersection / union if union else 0.0,
                "predicted_area_precision": intersection / prediction.area if prediction.area else 0.0,
                "reference_area_recall": intersection / reference.area if reference.area else 0.0,
            }
        )
    pairs = pd.DataFrame(pairs)
    predicted_overlay, reference_overlay, totals = _overlay_rows(prediction_polygons, reference_polygons)
    relations = _qualifying_relations(prediction_polygons, reference_polygons)
    qualified_predictions = relations["prediction_index"].nunique() if not relations.empty else 0
    qualified_references = relations["reference_index"].nunique() if not relations.empty else 0
    qualified_precision = qualified_predictions / len(predictions) if len(predictions) else 0.0
    qualified_recall = qualified_references / len(references) if len(references) else 0.0
    qualified_f1 = (
        2 * qualified_precision * qualified_recall / (qualified_precision + qualified_recall)
        if qualified_precision + qualified_recall
        else 0.0
    )

    pairs_path = result_dir / "anchorage_comparison_pairs.csv"
    predicted_overlay_path = result_dir / "anchorage_overlay_by_prediction.csv"
    reference_overlay_path = result_dir / "anchorage_overlay_by_reference.csv"
    relations_path = result_dir / "anchorage_qualifying_spatial_relations.csv"
    pairs.to_csv(pairs_path, index=False)
    predicted_overlay.to_csv(predicted_overlay_path, index=False)
    reference_overlay.to_csv(reference_overlay_path, index=False)
    relations.to_csv(relations_path, index=False)

    def metric(column: str, statistic: str) -> float:
        return float(pairs[column].agg(statistic)) if not pairs.empty else 0.0

    report = f"""# 预测锚地与处理后真实锚地对比：{result_dir.name}

## 评估口径

- 真实锚地使用 `data/reference/实际数据/processed/中国锚地_去重.csv`：已删除近乎完全覆盖的重复面，并裁掉与更大面重叠的部分。
- 中心一对一匹配半径为 {match_radius_m / 1000:.0f} km；中心指标用于辅助定位，不作为唯一正确性判断。
- 面积指标与“预测合格率”均在 EPSG:3857 米制坐标计算。面之间有大于 {QUALIFYING_OVERLAP_MIN_M2:.0f} ㎡ 的交集即为有效相交。

## 中心一对一匹配

| 指标 | 数值 |
| --- | ---: |
| 预测锚地 | {len(predictions)} |
| 真实锚地 | {len(references)} |
| 一对一匹配对 | {len(pairs)} |
| 中心距离中位数 | {metric('center_distance_m', 'median'):.0f} m |
| 中心距离 P90 | {metric('center_distance_m', 'quantile') if False else (pairs['center_distance_m'].quantile(0.9) if not pairs.empty else 0):.0f} m |
| IoU 中位数 | {metric('iou', 'median'):.3f} |
| 单对预测面积精度中位数 | {metric('predicted_area_precision', 'median'):.3f} |
| 单对真实面积召回中位数 | {metric('reference_area_recall', 'median'):.3f} |

## 多对多范围准确性

| 指标 | 结果 |
| --- | ---: |
| 预测面积精度（全局并集） | {totals['global_precision']:.3f} |
| 真实面积召回（全局并集） | {totals['global_recall']:.3f} |
| 面范围 IoU（全局并集） | {totals['global_iou']:.3f} |
| 预测合格率 | {qualified_predictions} / {len(predictions)} ({qualified_precision:.1%}) |
| 真实锚地发现率 | {qualified_references} / {len(references)} ({qualified_recall:.1%}) |
| 合格率 F1 | {qualified_f1:.3f} |

“预测合格率”衡量预测面是否落入任一真实锚地，“真实锚地发现率”衡量真实面是否被任一预测面触及；全局面积精度、召回和 IoU 则评价范围大小与位置。逐对中心匹配见 `anchorage_comparison_pairs.csv`，多对多覆盖明细见 `anchorage_overlay_by_prediction.csv`、`anchorage_overlay_by_reference.csv` 和 `anchorage_qualifying_spatial_relations.csv`。
"""
    report_path = result_dir / "anchorage_comparison.md"
    report_path.write_text(report, encoding="utf-8")
    return {
        "report": report_path,
        "pairs": pairs_path,
        "predicted_overlay": predicted_overlay_path,
        "reference_overlay": reference_overlay_path,
        "qualifying_relations": relations_path,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--match-radius-m", type=float, default=DEFAULT_MATCH_RADIUS_M)
    args = parser.parse_args()
    paths = evaluate(args.result_dir, args.match_radius_m)
    print(f"已写入：{paths['report']}")
    print(f"已写入：{paths['pairs']}")


if __name__ == "__main__":
    main()
