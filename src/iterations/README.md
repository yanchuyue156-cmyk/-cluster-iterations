# 参数迭代

此目录保存每轮可复跑的参数方案。公共算法只能在 `src/common/pipeline.py` 中维护一份；每个迭代文件仅记录与默认参数不同的值，避免复制整份流程代码。

## 新建一轮迭代

复制 `iteration_01_baseline.py`，按顺序创建新文件，例如 `iteration_02_terminal_radius_1200m.py`：

```python
NAME = "iteration_02_terminal_radius_1200m"
DESCRIPTION = "验证将码头聚类半径从 1,000 米改为 1,200 米的影响。"
PARAMETER_OVERRIDES = {
    "terminal_eps_m": 1200.0,
}
```

只填写发生变化的参数。完整默认参数见项目根目录的 `参数说明.md`。

## 运行

```bash
# 运行基线方案
python -m src.iterations.run iteration_01_baseline

# 运行指定调参方案
python -m src.iterations.run iteration_02_terminal_radius_1200m

# AIS 输入更新后刷新停泊段缓存
python -m src.iterations.run iteration_02_terminal_radius_1200m --refresh-cache
```

每轮迭代只能成功输出一次，结果目录与迭代文件同名，例如：

```text
src/iterations/iteration_02_terminal_radius_1200m.py
results/iterations/iteration_02_terminal_radius_1200m/
```

运行器会先写入临时目录，只有整个流程成功后才会生成上述结果目录。同名结果已存在时会拒绝覆盖；代码或参数有变化时，请新建下一轮迭代文件。

## 当前优化约束

从锚地优化开始，泊位与码头识别已经固定。创建锚地相关 iteration 时，不得修改任何泊位或码头相关参数、中心计算或范围生成规则（包括 `berth_*`、`terminal_*`）；只允许调整锚地识别、锚地聚类、锚地范围和锚地过滤规则。泊位与码头结果应作为锚地识别的固定排除参考。

导出该轮结果到地图看板时，明确指定对应结果目录：

```bash
.venv/bin/python -m src.common.export_dashboard_data \
  --result-dir results/iterations/iteration_02_terminal_radius_1200m
```

导出后会生成同名看板目录：

```text
results/iterations/iteration_02_terminal_radius_1200m/
dashboard/iterations/iteration_02_terminal_radius_1200m/
```

`legacy/` 保存整理前的历史实验脚本，仅用于回溯，不作为迭代模板或正式入口。
