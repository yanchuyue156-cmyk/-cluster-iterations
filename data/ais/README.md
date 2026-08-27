# AIS 输入数据（不纳入 Git）

`cleaned/data/` 中的 AIS CSV 是本项目的本地输入，体积约 3 GB，因此不会提交到仓库。

## 只查看结果

克隆仓库后无需准备 AIS。运行以下命令即可查看已提交的全部迭代看板：

```bash
python3 -m http.server 8000 --directory dashboard
```

浏览器打开 <http://localhost:8000>。

## 重新运行聚类

先从共享网盘、对象存储同步目录或移动硬盘取得包含 AIS CSV 的目录，再执行：

```bash
./scripts/sync_ais_data.sh /path/to/ais-source
```

脚本要求源目录中直接包含 CSV，或包含 `cleaned/data/` 层级；它会将 CSV 复制到本项目约定的 `data/ais/cleaned/data/`。复制完成后安装依赖并运行相应的聚类入口即可。

请勿把 AIS CSV 加入 Git 或 Git LFS。新增或替换数据时，应在团队共享存储中维护版本、来源和校验信息。
