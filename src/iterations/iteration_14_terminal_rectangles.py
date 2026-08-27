"""第 14 轮：将预测码头的范围面改为矩形。"""

NAME = "iteration_14_terminal_rectangles"
DESCRIPTION = (
    "保持第 13 轮的泊位、锚地和码头聚类规则；仅将已识别码头的展示范围面改为矩形，"
    "不改变码头归属、AIS 中心或任何聚类阈值。"
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
    # 码头的聚类和中心规则均不变，仅范围面矩形化。
    "terminal_max_span_m": 3000.0,
    "terminal_outline_buffer_m": 500.0,
    "terminal_shape_method": "bounding_rectangle",
}
