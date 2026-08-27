# 船舶 AIS 停泊点聚类

本项目使用清洗后的 AIS 数据识别停泊段、泊位、码头与锚地，并可用真实码头/锚地数据进行对照。

## 目录

- `src/common/`：稳定、正式的公共代码；入口为 `src/common/main.py`，所有模块共用 `src/common/paths.py` 中的统一路径。
- `src/iterations/`：可复跑的调参方案；每一轮仅记录相对默认值的参数变化，运行器为 `src/iterations/run.py`。
- `data/ais/cleaned/data/`：清洗后的 AIS 输入 CSV。
- `data/reference/实际数据/`：真实码头与锚地对照数据，不应被算法输出覆盖。
- `data/geospatial/`：海岸线和国界 Shapefile 底图。
- `results/`：算法和实验输出。
  - 每次正式运行自动创建下一个两位编号目录，如 `01/`、`02/`。
  - `results/README.md` 记录每一个编号版本的算法改动和用途；`cache/` 会保存停泊段缓存，加快后续运行。
- `dashboard/`：交互式地图看板；`index.html` 是所有迭代看板的目录入口，当前参数版为第 15 轮。第 13 轮参数汇报和离线汇报是固定历史快照。

## 脚本入口

- `python -m src.common.main`：正式入口，识别泊位、锚地与码头并输出至自动生成的下一个编号目录。
- `python -m src.common.main --refresh-cache`：原始 AIS 有更新时，重新读取并生成停泊段缓存。
- `python -m src.common.main --workers 4`：读取压力较大时将并发读取线程改为 4。
- `python -m src.iterations.run iteration_01_baseline`：按已记录的基线参数运行；新增调参方案的方式见 `src/iterations/README.md`。

旧实验脚本收纳在 `src/iterations/legacy/`，仅供回溯；请不要将它们作为正式入口。

所有默认参数及其含义见 [参数说明.md](参数说明.md)。

运行完整聚类前，在项目根目录创建环境并安装依赖：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

正式流程使用 `pandas`、`geopandas`、`scikit-learn` 及其自动安装的空间计算依赖。

## 地图看板

导出当前参数迭代（第 15 轮）的看板数据：

```bash
.venv/bin/python -m src.common.export_dashboard_data
python3 -m http.server 8000 --directory dashboard
```

然后在浏览器打开 `http://localhost:8000`。也可以直接双击 `dashboard/index.html`：看板会优先从同目录的 `data.js` 读取已导出的数据。地图底图使用 OpenStreetMap，因此首次查看需要网络连接。

若要重新导出某轮参数迭代的地图数据，指定对应结果目录：

```bash
.venv/bin/python -m src.common.export_dashboard_data \
  --result-dir results/iterations/iteration_01_baseline
```

该命令会生成同名迭代看板：`dashboard/iterations/iteration_01_baseline/`，并更新根目录的看板目录。启动本地服务后，在浏览器打开 `http://localhost:8000/`，或直接打开对应轮次的 `index.html`。
