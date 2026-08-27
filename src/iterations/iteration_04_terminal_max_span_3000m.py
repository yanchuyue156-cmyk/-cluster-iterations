"""第 04 轮：限制沿岸链式合并产生的超长码头。"""

NAME = "iteration_04_terminal_max_span_3000m"
DESCRIPTION = "保持第 03 轮中心与 500 米范围外扩；将单一码头的泊位中心最大跨度限制为 3,000 米。"

PARAMETER_OVERRIDES: dict[str, object] = {
    "terminal_max_span_m": 3000.0,
    "terminal_outline_buffer_m": 500.0,
}
