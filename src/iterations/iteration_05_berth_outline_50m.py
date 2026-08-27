"""第 05 轮：扩大 AIS 泊位活动范围面。"""

NAME = "iteration_05_berth_outline_50m"
DESCRIPTION = "保持第 04 轮的码头中心、3 km 最大跨度与 500 m 码头外扩；泊位活动范围额外向外扩展 50 米。"

PARAMETER_OVERRIDES: dict[str, object] = {
    "berth_outline_buffer_m": 50.0,
    "terminal_max_span_m": 3000.0,
    "terminal_outline_buffer_m": 500.0,
}
