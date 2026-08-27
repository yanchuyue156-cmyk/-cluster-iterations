"""第 02 轮：以 AIS 活动 medoid 作为泊位和码头中心。"""

NAME = "iteration_02_weighted_medoid_terminal_center"
DESCRIPTION = "泊位与码头中心改为停泊时长加权 medoid；聚类和范围参数保持基线不变。"

# 本轮验证的是中心计算代码，不改变 PipelineConfig 参数。
PARAMETER_OVERRIDES: dict[str, object] = {}
