"""第 15 轮：将相邻预测码头矩形切分为无重叠范围。"""

NAME = "iteration_15_terminal_non_overlapping_rectangles"
DESCRIPTION = (
    "保持第 14 轮的矩形码头、中心和聚类规则；沿相邻码头 AIS 中心的主方向切开矩形重叠区，"
    "使预测码头范围无面积重叠。"
)

PARAMETER_OVERRIDES: dict[str, object] = {
    # 保留第 13 轮泊位与锚地规则。
    "berth_outline_buffer_m": 50.0,
    "anchorage_eps_m": 8000.0,
    "anchorage_min_samples": 3,
    "anchorage_shape_method": "adaptive_point_buffer_union",
    "anchorage_adaptive_buffer_min_m": 2000.0,
    "anchorage_adaptive_buffer_max_m": 8000.0,
    "anchorage_adaptive_buffer_span_ratio": 0.40,
    "anchorage_simplify_m": 40.0,
    "anchorage_exclude_terminal_overlap": True,
    "anchorage_terminal_clearance_m": 5.0,
    "anchorage_exclude_land_overlap": True,
    "anchorage_land_clearance_m": 5.0,
    "anchorage_use_land_boundary_distance": True,
    "anchorage_open_water_only": True,
    "anchorage_coast_min_m": 3000.0,
    "anchorage_coast_max_m": 20000.0,
    # 仅对第 14 轮矩形码头做互斥切分；聚类、中心、外扩距离均不变。
    "terminal_max_span_m": 3000.0,
    "terminal_outline_buffer_m": 500.0,
    "terminal_shape_method": "bounding_rectangle",
    "terminal_resolve_rectangle_overlaps": True,
}
