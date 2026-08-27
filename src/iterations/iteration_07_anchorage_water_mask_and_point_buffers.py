"""第 07 轮：锚地限制在水域，并使用圆角外边界。"""

NAME = "iteration_07_anchorage_water_mask_and_point_buffers"
DESCRIPTION = "保持第 05 轮泊位和码头规则不变；锚地排除陆地与码头范围，并以圆角外边界替代凹包。"

PARAMETER_OVERRIDES: dict[str, object] = {
    # 固定已确认的泊位与码头规则；本轮不调整它们。
    "berth_outline_buffer_m": 50.0,
    "terminal_max_span_m": 3000.0,
    "terminal_outline_buffer_m": 500.0,
    # 保留第 06 轮的固定码头排除。
    "anchorage_exclude_terminal_overlap": True,
    "anchorage_terminal_clearance_m": 5.0,
    # 本轮锚地优化：水域掩膜 + 非凹包的圆角范围面。
    "anchorage_shape_method": "point_buffer_union",
    "anchorage_exclude_land_overlap": True,
    "anchorage_land_clearance_m": 5.0,
}
