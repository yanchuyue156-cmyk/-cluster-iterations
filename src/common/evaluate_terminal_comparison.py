"""Evaluate one iteration's predicted terminal areas against reference terminal areas."""

from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
from shapely import from_wkt, make_valid

try:
    from .paths import CHINA_SHP, REFERENCE_DIR
except ImportError:  # pragma: no cover
    from paths import CHINA_SHP, REFERENCE_DIR


METRIC_CRS = "EPSG:3857"
REFERENCE_COASTAL_BUFFER_M = 50_000.0
QUALIFYING_OVERLAP_MIN_M2 = 1.0


def _china_geometry():
    countries = gpd.read_file(CHINA_SHP)
    return countries.loc[countries["NAME"].isin(["China", "Taiwan"])].to_crs(METRIC_CRS).union_all()


def _reference_path() -> Path:
    china_version = REFERENCE_DIR / "实际数据中国版" / "码头.csv"
    return china_version if china_version.exists() else REFERENCE_DIR / "码头.csv"


def _valid(geometry):
    return geometry if geometry.is_valid else make_valid(geometry)


def _load_reference() -> tuple[pd.DataFrame, gpd.GeoSeries, gpd.GeoSeries, int]:
    reference = pd.read_csv(_reference_path(), encoding="utf-8-sig")
    points = gpd.GeoSeries.from_wkt(reference["point"], crs="EPSG:4326").to_crs(METRIC_CRS)
    polygons = gpd.GeoSeries.from_wkt(reference["geom"], crs="EPSG:4326").to_crs(METRIC_CRS)
    # 码头的代表点常落在泊位水域；用近岸海域缓冲而非纯陆地边界筛选参考记录。
    within_evaluation_area = points.within(_china_geometry().buffer(REFERENCE_COASTAL_BUFFER_M))
    excluded = int((~within_evaluation_area).sum())
    return (
        reference.loc[within_evaluation_area].reset_index(drop=True),
        points.loc[within_evaluation_area].reset_index(drop=True),
        polygons.loc[within_evaluation_area].map(_valid).reset_index(drop=True),
        excluded,
    )


def _load_predictions(result_dir: Path) -> tuple[pd.DataFrame, gpd.GeoSeries, gpd.GeoSeries]:
    predictions = pd.read_csv(result_dir / "china_terminals.csv")
    points = gpd.GeoSeries(
        gpd.points_from_xy(predictions["lon"], predictions["lat"]), crs="EPSG:4326"
    ).to_crs(METRIC_CRS)
    polygons = gpd.GeoSeries.from_wkt(predictions["polygon"], crs="EPSG:4326").to_crs(METRIC_CRS)
    return predictions, points, polygons.map(_valid)


def _one_to_one_match(
    prediction_points: gpd.GeoSeries,
    reference_points: gpd.GeoSeries,
    radius_m: float,
) -> list[tuple[int, int, float]]:
    """在半径内寻找总中心距离最小的一对一匹配，未匹配预测连到虚拟列。"""
    pred_xy = np.column_stack((prediction_points.x, prediction_points.y))
    ref_xy = np.column_stack((reference_points.x, reference_points.y))
    distances = np.hypot(
        pred_xy[:, None, 0] - ref_xy[None, :, 0],
        pred_xy[:, None, 1] - ref_xy[None, :, 1],
    )
    unavailable = radius_m * 1000
    # 每个预测码头都可匹配一个虚拟列；这比强行配对远距离真实码头更稳妥。
    costs = np.full((len(pred_xy), len(ref_xy) + len(pred_xy)), unavailable, dtype="float64")
    costs[:, : len(ref_xy)] = np.where(distances <= radius_m, distances, unavailable)
    costs[:, len(ref_xy) :] = radius_m
    rows, columns = linear_sum_assignment(costs)
    return [
        (int(row), int(column), float(distances[row, column]))
        for row, column in zip(rows, columns)
        if column < len(ref_xy) and distances[row, column] <= radius_m
    ]


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def _relaxed_overlay(
    prediction_polygons: gpd.GeoSeries, reference_polygons: gpd.GeoSeries
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    """计算不限制一对一关系的面覆盖，适合码头粒度不完全一致的场景。"""
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

    predicted_overlay = pd.DataFrame(predicted_rows)
    reference_overlay = pd.DataFrame(reference_rows)
    prediction_union = prediction_polygons.union_all()
    reference_union = reference_polygons.union_all()
    global_intersection = prediction_union.intersection(reference_union).area
    global_union = prediction_union.union(reference_union).area
    totals = {
        "global_iou": global_intersection / global_union if global_union else 0.0,
        "global_precision": global_intersection / prediction_union.area if prediction_union.area else 0.0,
        "global_recall": global_intersection / reference_union.area if reference_union.area else 0.0,
    }
    return predicted_overlay, reference_overlay, totals


def _qualifying_spatial_relations(
    prediction_polygons: gpd.GeoSeries, reference_polygons: gpd.GeoSeries
) -> pd.DataFrame:
    """返回用户定义的合格关系：两面必须拥有正面积交集，不把边界接触算作命中。"""
    reference_index = reference_polygons.sindex
    relations = []
    for prediction_index, prediction in prediction_polygons.items():
        candidates = reference_index.query(prediction, predicate="intersects")
        for reference_index_value in candidates:
            reference = reference_polygons.iloc[reference_index_value]
            overlap_area = prediction.intersection(reference).area
            if overlap_area <= QUALIFYING_OVERLAP_MIN_M2:
                continue
            if prediction.covers(reference) and reference.covers(prediction):
                relation = "范围相同"
            elif prediction.covers(reference):
                relation = "预测包含真实"
            elif reference.covers(prediction):
                relation = "真实包含预测"
            else:
                relation = "部分重叠"
            relations.append(
                {
                    "prediction_index": prediction_index,
                    "reference_index": int(reference_index_value),
                    "overlap_area_m2": overlap_area,
                    "relation": relation,
                }
            )
    return pd.DataFrame(relations)


def evaluate(result_dir: Path, radius_m: float = 2000.0) -> dict[str, Path]:
    predictions, prediction_points, prediction_polygons = _load_predictions(result_dir)
    references, reference_points, reference_polygons, reference_excluded = _load_reference()
    matches = _one_to_one_match(prediction_points, reference_points, radius_m)

    records = []
    for prediction_index, reference_index, distance_m in matches:
        predicted_area = float(prediction_polygons.iloc[prediction_index].area)
        reference_area = float(reference_polygons.iloc[reference_index].area)
        intersection_area = float(
            prediction_polygons.iloc[prediction_index]
            .intersection(reference_polygons.iloc[reference_index])
            .area
        )
        union_area = predicted_area + reference_area - intersection_area
        records.append(
            {
                "terminal_id": predictions.iloc[prediction_index]["terminal_id"],
                "reference_pid": references.iloc[reference_index]["pid"],
                "reference_name": references.iloc[reference_index]["name"],
                "center_distance_m": distance_m,
                "predicted_area_m2": predicted_area,
                "reference_area_m2": reference_area,
                "area_ratio_predicted_to_reference": predicted_area / reference_area,
                "intersection_area_m2": intersection_area,
                "iou": intersection_area / union_area if union_area else 0.0,
                "predicted_area_precision": intersection_area / predicted_area if predicted_area else 0.0,
                "reference_area_recall": intersection_area / reference_area if reference_area else 0.0,
            }
        )

    pairs = pd.DataFrame(records)
    if pairs.empty:
        raise ValueError("没有在匹配半径内的一对一预测/实际码头对")
    pairs_path = result_dir / "terminal_comparison_pairs.csv"
    pairs.to_csv(pairs_path, index=False)

    predicted_overlay, reference_overlay, overlay_totals = _relaxed_overlay(
        prediction_polygons, reference_polygons
    )
    predicted_overlay_path = result_dir / "terminal_overlay_by_prediction.csv"
    reference_overlay_path = result_dir / "terminal_overlay_by_reference.csv"
    predicted_overlay.to_csv(predicted_overlay_path, index=False)
    reference_overlay.to_csv(reference_overlay_path, index=False)
    qualifying_relations = _qualifying_spatial_relations(prediction_polygons, reference_polygons)
    qualifying_path = result_dir / "terminal_qualifying_spatial_relations.csv"
    qualifying_relations.to_csv(qualifying_path, index=False)
    qualified_predictions = qualifying_relations["prediction_index"].nunique()
    qualified_references = qualifying_relations["reference_index"].nunique()
    relation_counts = qualifying_relations["relation"].value_counts()

    ratio = pairs["area_ratio_predicted_to_reference"]
    smaller = int((ratio < 1).sum())
    larger = int((ratio > 1).sum())
    matched_predictions = len(pairs)
    matched_references = pairs["reference_pid"].nunique()
    report = f"""# 预测码头与真实码头对比：{result_dir.name}

## 匹配方法

1. 预测码头使用 `china_terminals.csv` 的 AIS 活动中心（`lat`、`lon`）与预测范围面。
2. 真实码头使用参考数据的 `point` 作为中心、`geom` 作为范围面。
3. 真实码头中心可位于近岸水域，因此评估范围为中国与台湾陆地及其 {REFERENCE_COASTAL_BUFFER_M / 1000:.0f} km 近岸海域；落在范围外的参考记录不删除，只是不参与本次中国范围评估。
4. 只保留两中心距离不超过 {radius_m:,.0f} m 的候选对，并采用最小总中心距离的一对一匹配。每个预测码头和每个真实码头最多匹配一次；不能在半径内匹配的对象视为未匹配。
5. 所有面积与叠加指标均在 EPSG:3857 米制坐标中计算。

## 覆盖与匹配

| 项目 | 数量 |
| --- | ---: |
| 预测码头 | {len(predictions)} |
| 参考码头原始记录 | {len(references) + reference_excluded} |
| 因中心在中国及 {REFERENCE_COASTAL_BUFFER_M / 1000:.0f} km 近岸海域外而不参与评估的参考记录 | {reference_excluded} |
| 参与评估的参考码头 | {len(references)} |
| 一对一匹配对 | {matched_predictions} |
| 未匹配预测码头 | {len(predictions) - matched_predictions} |
| 未匹配参考码头 | {len(references) - matched_references} |

## 中心位置

| 指标 | 数值 |
| --- | ---: |
| 中心距离中位数 | {pairs['center_distance_m'].median():.0f} m |
| 中心距离 P90 | {pairs['center_distance_m'].quantile(0.9):.0f} m |

## 面积

面积比定义为 `预测面积 / 真实面积`。

| 指标 | 数量/数值 |
| --- | ---: |
| 预测面积小于真实面积 | {smaller} ({_percent(smaller / matched_predictions)}) |
| 预测面积大于真实面积 | {larger} ({_percent(larger / matched_predictions)}) |
| 面积比中位数 | {ratio.median():.3f} |
| 面积比 P25 / P75 | {ratio.quantile(0.25):.3f} / {ratio.quantile(0.75):.3f} |
| 面积在真实面积 0.5--2 倍内 | {int(((ratio >= 0.5) & (ratio <= 2)).sum())} ({_percent(((ratio >= 0.5) & (ratio <= 2)).mean())}) |

## 形状重叠

- IoU = `预测面与真实面交集 / 两者并集`，越接近 1 表示形状与位置越一致。
- 预测面积精度 = `交集 / 预测面积`，用于判断预测范围有多少落在真实范围内。
- 真实面积召回 = `交集 / 真实面积`，用于判断真实范围被预测覆盖了多少。

| 指标 | 中位数 | P90 |
| --- | ---: | ---: |
| IoU | {pairs['iou'].median():.3f} | {pairs['iou'].quantile(0.9):.3f} |
| 预测面积精度 | {pairs['predicted_area_precision'].median():.3f} | {pairs['predicted_area_precision'].quantile(0.9):.3f} |
| 真实面积召回 | {pairs['reference_area_recall'].median():.3f} | {pairs['reference_area_recall'].quantile(0.9):.3f} |

## 放宽的一对多/多对多范围覆盖

这一层不使用中心距离，也不限制一对一关系：只要预测面与真实面有交集，就共同参与覆盖面积计算。它回答的是“所有紫色预测面合起来，覆盖了多少绿色真实面”，适合预测码头与参考码头的拆分粒度不同的情形。

| 指标 | 数值 |
| --- | ---: |
| 与至少一个真实面相交的预测码头 | {int((predicted_overlay['overlapping_reference_count'] > 0).sum())} / {len(predicted_overlay)} |
| 被至少一个预测面相交的真实码头 | {int((reference_overlay['overlapping_prediction_count'] > 0).sum())} / {len(reference_overlay)} |
| 预测面覆盖精度（全局并集） | {overlay_totals['global_precision']:.3f} |
| 真实面覆盖召回（全局并集） | {overlay_totals['global_recall']:.3f} |
| 面范围 IoU（全局并集） | {overlay_totals['global_iou']:.3f} |
| 单个真实码头覆盖率中位数 | {reference_overlay['reference_area_recall'].median():.3f} |

逐对严格匹配见 `terminal_comparison_pairs.csv`；多对多覆盖明细见 `terminal_overlay_by_prediction.csv` 和 `terminal_overlay_by_reference.csv`。该报告评价的是参考数据中记录的码头范围与 AIS 推断活动范围的一致性，不应被解释为法定或运营边界的真值判定。

## 用户定义的“预测合格率”

本指标不要求预测面与真实面形状、面积或拆分粒度相同，也不要求一对一匹配。只要一张预测面与任意一张真实面拥有大于 {QUALIFYING_OVERLAP_MIN_M2:.0f} ㎡ 的共同面积，就计为合格；只有边界相碰、没有共同面积的情况不计入。

| 指标 | 计算方式 | 结果 |
| --- | --- | ---: |
| 预测合格率 | 至少与一个真实面有效相交的预测码头 / 全部预测码头 | {qualified_predictions} / {len(predictions)} ({_percent(qualified_predictions / len(predictions))}) |
| 真实码头发现率 | 至少与一个预测面有效相交的真实码头 / 全部真实码头 | {qualified_references} / {len(references)} ({_percent(qualified_references / len(references))}) |
| 合格空间关系对 | 所有有效相交的预测/真实面组合 | {len(qualifying_relations)} |

| 合格关系 | 组合数 |
| --- | ---: |
| 预测包含真实 | {int(relation_counts.get('预测包含真实', 0))} |
| 真实包含预测 | {int(relation_counts.get('真实包含预测', 0))} |
| 部分重叠 | {int(relation_counts.get('部分重叠', 0))} |
| 范围相同 | {int(relation_counts.get('范围相同', 0))} |

详细的每一组空间关系见 `terminal_qualifying_spatial_relations.csv`。
"""
    report_path = result_dir / "terminal_comparison.md"
    report_path.write_text(report, encoding="utf-8")
    return {
        "report": report_path,
        "pairs": pairs_path,
        "predicted_overlay": predicted_overlay_path,
        "reference_overlay": reference_overlay_path,
        "qualifying_relations": qualifying_path,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--match-radius-m", type=float, default=2000.0)
    args = parser.parse_args()
    paths = evaluate(args.result_dir, args.match_radius_m)
    print(f"已写入：{paths['report']}")
    print(f"已写入：{paths['pairs']}")


if __name__ == "__main__":
    main()
