"""第 06 轮：用固定码头范围排除锚地与码头重叠。"""

NAME = "iteration_06_anchorage_terminal_exclusion"
DESCRIPTION = "保持第 05 轮泊位和码头规则不变；剔除中心位于码头内的锚地，并从其余锚地范围中裁掉码头区域。"

PARAMETER_OVERRIDES: dict[str, object] = {
    # 固定已确认的泊位与码头规则；本轮不调整它们。
    "berth_outline_buffer_m": 50.0,
    "terminal_max_span_m": 3000.0,
    "terminal_outline_buffer_m": 500.0,
    # 本轮唯一新增的锚地约束。
    "anchorage_exclude_terminal_overlap": True,
    "anchorage_terminal_clearance_m": 5.0,
}
