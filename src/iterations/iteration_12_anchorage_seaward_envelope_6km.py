"""第 12 轮：收紧锚地向外海延伸的范围。"""

NAME = "iteration_12_anchorage_seaward_envelope_6km"
DESCRIPTION = (
    "保持第 11 轮的 8 km 锚地连通聚类与水域裁切；将 AIS 点群外包络从 10 km 收紧为 6 km，"
    "减少跨越无 AIS 支撑海域的过大预测面。"
)

PARAMETER_OVERRIDES: dict[str, object] = {
    # 固定已确认的泊位与码头规则；本轮不调整它们。
    "berth_outline_buffer_m": 50.0,
    "terminal_max_span_m": 3000.0,
    "terminal_outline_buffer_m": 500.0,
    # 保留第 11 轮的锚地连通性，仅收紧范围面外扩。
    "anchorage_eps_m": 8000.0,
    "anchorage_min_samples": 3,
    "anchorage_shape_method": "point_buffer_union",
    "anchorage_outline_buffer_m": 6000.0,
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
