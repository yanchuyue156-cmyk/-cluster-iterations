"""第 08 轮：以 AIS 中心生成圆润锚地，并限制在开阔水域。"""

NAME = "iteration_08_anchorage_center_open_water"
DESCRIPTION = "保持第 05 轮泊位和码头规则不变；锚地使用时长加权 AIS 中心和自适应圆形范围，并将距陆地边界不足既有 3 km 阈值的内河/贴岸部分排除。"

PARAMETER_OVERRIDES: dict[str, object] = {
    # 固定已确认的泊位与码头规则；本轮不调整它们。
    "berth_outline_buffer_m": 50.0,
    "terminal_max_span_m": 3000.0,
    "terminal_outline_buffer_m": 500.0,
    # 保留第 06、07 轮的固定排除。
    "anchorage_exclude_terminal_overlap": True,
    "anchorage_terminal_clearance_m": 5.0,
    "anchorage_exclude_land_overlap": True,
    "anchorage_land_clearance_m": 5.0,
    # 第 08 轮只优化锚地：中心化圆润范围 + 开阔水域约束。
    "anchorage_shape_method": "center_buffer",
    "anchorage_use_land_boundary_distance": True,
    "anchorage_open_water_only": True,
}
