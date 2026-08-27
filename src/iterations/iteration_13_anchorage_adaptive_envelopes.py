"""第 13 轮：按 AIS 点群跨度自适应生成锚地外海包络。"""

NAME = "iteration_13_anchorage_adaptive_envelopes"
DESCRIPTION = (
    "保持第 12 轮的 8 km 锚地连通聚类与水域裁切；锚地外扩距离按各 AIS 点群跨度自适应计算，"
    "限制在 2--8 km，避免紧凑点群被统一 6 km 缓冲放大。"
)

PARAMETER_OVERRIDES: dict[str, object] = {
    # 固定已确认的泊位与码头规则；本轮不调整它们。
    "berth_outline_buffer_m": 50.0,
    "terminal_max_span_m": 3000.0,
    "terminal_outline_buffer_m": 500.0,
    # 保留第 12 轮的连通尺度；最大跨度切分经过验证会损失真实大锚地，故不启用。
    "anchorage_eps_m": 8000.0,
    "anchorage_min_samples": 3,
    # 外扩距离 = 点群包络对角线的 40%，并夹在 2--8 km 之间。
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
}
