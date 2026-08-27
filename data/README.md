# 数据目录说明

本目录保存算法运行所需的输入、对照资料和地理空间参考数据。

- `ais/cleaned/data/`：清洗后的 AIS 输入数据。
- `reference/实际数据/`：用于核对的真实数据。
- `reference/实际数据/processed/中国锚地_去重.csv`：后续 iteration 看板与评估统一使用的真实锚地参考数据；较小范围被较大范围覆盖 ≥95% 时删除较小记录，原始数据不覆盖。`中国锚地_去重记录.csv` 保存删除审计记录。
- `geospatial/ne_10m_admin_0_countries/`：Natural Earth 国家边界底图。
- `geospatial/ne_10m_coastline/`：Natural Earth 海岸线底图。它不完整表达河口潮汐水域两侧岸线。

除非创建新的数据版本，不要覆盖既有 AIS 输入或已校验的原始下载文件。
