"""第 10 轮：按 AIS 停泊分布生成向深海延伸的锚地范围。"""

NAME = "iteration_10_anchorage_seaward_envelopes"
DESCRIPTION = (
    "保持已确认的泊位与码头规则不变；锚地改用 AIS 停泊点凸包的 3 km 圆角外包络，"
    "并将开阔水域阈值应用于整个范围面而非仅中心，以保留向深海延伸的锚地。"
)

PARAMETER_OVERRIDES: dict[str, object] = {
    # 固定已确认的泊位与码头规则；本轮不调整它们。
    "berth_outline_buffer_m": 50.0,
    "terminal_max_span_m": 3000.0,
    "terminal_outline_buffer_m": 500.0,
    # 锚地：降低密度门槛以找回有 3--4 个有效停泊段的锚地；保留既有 6 km 连通尺度。
    "anchorage_min_samples": 3,
    "anchorage_eps_m": 6000.0,
    # 不再围绕中心画圆；由 AIS 停泊点分布形成带方向的凸包，外扩 3 km 后再裁掉陆地。
    "anchorage_shape_method": "point_buffer_union",
    "anchorage_outline_buffer_m": 3000.0,
    "anchorage_simplify_m": 40.0,
    # 保留第 08--09 轮水域与码头排除。开阔水域模式会将 3 km 阈值作用于整个面，
    # 中心靠岸但向外海延伸的锚地不会因此被整块删除。
    "anchorage_exclude_terminal_overlap": True,
    "anchorage_terminal_clearance_m": 5.0,
    "anchorage_exclude_land_overlap": True,
    "anchorage_land_clearance_m": 5.0,
    "anchorage_use_land_boundary_distance": True,
    "anchorage_open_water_only": True,
    "anchorage_coast_min_m": 3000.0,
    "anchorage_coast_max_m": 20000.0,
}
