# 结果目录说明

直接运行正式入口时，结果目录使用两位编号。参数迭代运行则使用 `results/iterations/<迭代名>/`，并与对应的 `src/iterations/<迭代名>.py` 一一对应；两类结果均不得覆盖。

## 已清理的历史编号结果

`01` 至 `07` 是整理前的正式流程输出，已于 2026-08-27 清理。根目录 `dashboard/` 中仍保留基于 `07` 导出的静态历史看板；所有可复核的参数迭代结果和对应看板均保存在下方的迭代目录中。

## 参数迭代版本

| 版本 | 来源与修改 | 泊位 | 锚地 | 码头 | 备注 |
| --- | --- | ---: | ---: | ---: | --- |
| iteration_01_baseline | 当前正式流程基线 | 1,427 | 120 | 720 | 码头中心为合并活动范围面的几何质心。 |
| iteration_02_weighted_medoid_terminal_center | AIS 活动中心 | 1,428 | 120 | 725 | 泊位中心为停泊时长加权 medoid；码头中心为泊位中心的时长加权 medoid。 |
| iteration_03_terminal_outline_500m | 码头活动范围外扩 | 1,428 | 120 | 725 | 中心和泊位归属与第 02 轮相同；码头活动范围面额外向外扩展 500 米。 |
| iteration_04_terminal_max_span_3000m | 抑制沿岸链式合并 | 1,428 | 120 | 738 | 保持 500 米范围外扩；单一码头泊位中心的最大直线跨度限制为 3,000 米。 |
| iteration_05_berth_outline_50m | 泊位活动范围外扩 | 1,428 | 120 | 738 | 保持第 04 轮码头规则；泊位活动范围面额外向外扩展 50 米。 |
| iteration_06_anchorage_terminal_exclusion | 锚地排除码头范围 | 1,428 | 110 | 738 | 泊位和码头结果保持第 05 轮不变；锚地中心入港者剔除，其余锚地范围裁掉固定码头区域。 |
| iteration_07_anchorage_water_mask_and_point_buffers | 锚地水域约束与圆角范围 | 1,428 | 106 | 738 | 泊位和码头结果与第 05 轮保持一致；锚地中心不得落在陆地或码头内，范围裁掉陆地/码头，并以圆角外边界替代凹包。 |
| iteration_08_anchorage_center_open_water | 锚地中心与开阔水域 | 1,428 | 95 | 738 | 泊位和码头结果与第 05 轮逐字一致；锚地中心改为时长加权 AIS medoid，范围为自适应圆形，并裁掉距陆地边界不足既有 3 km 的内河/贴岸部分。 |
| iteration_09_anchorage_expanded_center_range | 扩大锚地中心范围 | 1,428 | 95 | 738 | 保持第 08 轮中心与开阔水域约束；范围由覆盖中心周围 50% 的停泊时长扩大为 90%，看板真实锚地改用 95% 覆盖去重后的 136 条参考数据。 |
| iteration_10_anchorage_seaward_envelopes | 锚地向海包络 | 1,428 | 131 | 738 | 在第 09 轮基础上调整锚地范围，使其向外海延伸。 |
| iteration_11_anchorage_seaward_envelope_10km | 10 km 向海包络 | 1,428 | 104 | 738 | 将锚地向海外扩的最大距离设为 10 km。 |
| iteration_12_anchorage_seaward_envelope_6km | 6 km 向海包络 | 1,428 | 104 | 738 | 将锚地向海外扩的最大距离收紧为 6 km。 |
| iteration_13_anchorage_adaptive_envelopes | 自适应锚地包络 | 1,428 | 104 | 738 | 按 AIS 点群跨度生成 2–8 km 的自适应圆角外包络；第 13 轮参数汇报固定保留。 |
| iteration_14_terminal_rectangles | 码头矩形范围 | 1,428 | 104 | 738 | 保持第 13 轮锚地规则，码头范围改为严格矩形。 |
| iteration_15_terminal_non_overlapping_rectangles | 码头无重叠矩形 | 1,428 | 104 | 738 | 在第 14 轮基础上切分相邻矩形的重叠区；这是当前参数版本。 |

## 当前规则

- `src.common.main` 不指定 `--output-dir` 时，会自动写入下一个编号目录。
- `src.iterations.run` 仅在迭代成功后写入 `results/iterations/<迭代名>/`；同名结果存在时会拒绝覆盖。
- 地图看板导出工具默认读取当前参数迭代（由 `src.common.paths.CURRENT_ITERATION_NAME` 指定）；查看或重导出其他轮次时，用 `--result-dir` 明确指定目录。
- 新建并确认一轮参数后，更新 `CURRENT_ITERATION_NAME`，再导出该轮看板；根目录 `dashboard/index.html` 会自动将其标记为当前参数。
- `cache/` 是停泊段缓存，不是结果版本，不参与编号。
