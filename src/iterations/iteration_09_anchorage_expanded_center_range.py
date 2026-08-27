"""第 09 轮：扩大以 AIS 中心为基础的锚地范围。"""

NAME = "iteration_09_anchorage_expanded_center_range"
DESCRIPTION = "保持第 08 轮的 AIS 中心与开阔水域约束；锚地范围从覆盖中心周围 50% 的停泊时长扩大为覆盖 90%，泊位和码头规则不变。"

PARAMETER_OVERRIDES: dict[str, object] = {
    # 固定已确认的泊位与码头规则；本轮不调整它们。
    "berth_outline_buffer_m": 50.0,
    "terminal_max_span_m": 3000.0,
    "terminal_outline_buffer_m": 500.0,
    # 保留第 08 轮锚地中心、水域与码头排除。
    "anchorage_exclude_terminal_overlap": True,
    "anchorage_terminal_clearance_m": 5.0,
    "anchorage_exclude_land_overlap": True,
    "anchorage_land_clearance_m": 5.0,
    "anchorage_shape_method": "center_buffer",
    "anchorage_use_land_boundary_distance": True,
    "anchorage_open_water_only": True,
    # 仅扩大锚地范围：覆盖停泊时长从中心向外的 90%。
    "anchorage_center_coverage_quantile": 0.90,
}
