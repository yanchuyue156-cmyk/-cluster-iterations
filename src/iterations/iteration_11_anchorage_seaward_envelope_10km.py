"""第 11 轮：扩大向外海开放水域延伸的锚地包络。"""

NAME = "iteration_11_anchorage_seaward_envelope_10km"
DESCRIPTION = (
    "保持泊位和码头规则不变；锚地采用 8 km 连通聚类与 AIS 点群 10 km 外包络，"
    "再以陆地边界裁掉近岸侧，得到向外海延伸的范围。"
)

PARAMETER_OVERRIDES: dict[str, object] = {
    # 固定已确认的泊位与码头规则；本轮不调整它们。
    "berth_outline_buffer_m": 50.0,
    "terminal_max_span_m": 3000.0,
    "terminal_outline_buffer_m": 500.0,
    # 锚地：将同一港外锚泊水域的邻近 AIS 点群连通，避免拆成多个局部小面。
    "anchorage_eps_m": 8000.0,
    "anchorage_min_samples": 3,
    # 先依 AIS 点群形成方向性凸包，再扩大到外海；陆地和 3 km 贴岸带在后续裁掉。
    "anchorage_shape_method": "point_buffer_union",
    "anchorage_outline_buffer_m": 10000.0,
    "anchorage_simplify_m": 40.0,
    "anchorage_exclude_terminal_overlap": True,
    "anchorage_terminal_clearance_m": 5.0,
    "anchorage_exclude_land_overlap": True,
    "anchorage_land_clearance_m": 5.0,
    "anchorage_use_land_boundary_distance": True,
    "anchorage_open_water_only": True,
    "anchorage_coast_min_m": 3000.0,
    "anchorage_coast_max_m": 20000.0,
}
