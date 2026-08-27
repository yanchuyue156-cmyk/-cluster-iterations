"""运行指定的参数迭代方案。"""
from __future__ import annotations

import argparse
import importlib
import shutil
from pathlib import Path
from tempfile import mkdtemp

from ..common.paths import ITERATION_RESULTS_DIR, iteration_result_dir
from ..common.pipeline import PipelineConfig, run_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行 AIS 识别参数迭代方案")
    parser.add_argument(
        "iteration",
        nargs="?",
        default="iteration_01_baseline",
        help="迭代模块名，例如 iteration_01_baseline",
    )
    parser.add_argument("--refresh-cache", action="store_true", help="重新生成停泊段缓存")
    parser.add_argument("--workers", type=int, default=8, help="AIS 读取线程数（默认 8）")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.workers < 1:
        raise ValueError("--workers 必须大于等于 1")

    module = importlib.import_module(f"{__package__}.{args.iteration}")
    overrides = getattr(module, "PARAMETER_OVERRIDES", {})
    config = PipelineConfig(workers=args.workers, **overrides)
    name = getattr(module, "NAME", args.iteration)
    description = getattr(module, "DESCRIPTION", "")
    output_dir = iteration_result_dir(name)
    if output_dir.exists():
        raise FileExistsError(
            f"迭代 {name} 已有成功结果：{output_dir}。"
            "代码或参数有变化时，请新建下一轮 iteration 文件，不覆盖已有结果。"
        )

    ITERATION_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(mkdtemp(prefix=f".{name}-", dir=ITERATION_RESULTS_DIR))
    print(f"运行迭代：{name}；{description}")
    try:
        run_pipeline(config, output_dir=staging_dir, refresh_cache=args.refresh_cache)
        staging_dir.rename(output_dir)
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    print(f"迭代结果：{output_dir}")


if __name__ == "__main__":
    main()
