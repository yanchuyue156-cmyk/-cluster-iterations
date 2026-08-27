"""第 03 轮：扩大已确定码头的活动范围面。"""

NAME = "iteration_03_terminal_outline_500m"
DESCRIPTION = "保持第 02 轮 AIS 活动中心与码头归属不变，仅将码头活动范围向外扩展 500 米。"

PARAMETER_OVERRIDES: dict[str, object] = {
    "terminal_outline_buffer_m": 500.0,
}
