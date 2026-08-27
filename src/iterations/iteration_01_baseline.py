"""第 01 轮：当前正式流程的基线参数。"""

NAME = "iteration_01_baseline"
DESCRIPTION = "当前正式流程的默认参数，作为后续调参对照基线。"

# 只写与 PipelineConfig 默认值不同的参数。
# 当前基线不覆盖任何参数。
PARAMETER_OVERRIDES: dict[str, object] = {}
