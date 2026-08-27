"""项目唯一的正式命令行入口。"""
from __future__ import annotations

import argparse
from pathlib import Path

try:
    from .pipeline import PipelineConfig, run_pipeline
except ImportError:  # 支持 `python src/common/main.py`
    from pipeline import PipelineConfig, run_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="识别中国范围内的 AIS 泊位、锚地和码头")
    parser.add_argument(
        "--output-dir", type=Path, default=None, help="结果目录（默认自动创建下一个编号目录）"
    )
    parser.add_argument("--refresh-cache", action="store_true", help="重新读取原始 AIS 并刷新停泊段缓存")
    parser.add_argument("--workers", type=int, default=8, help="AIS 读取线程数（默认 8）")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.workers < 1:
        raise ValueError("--workers 必须大于等于 1")
    run_pipeline(
        PipelineConfig(workers=args.workers),
        output_dir=args.output_dir,
        refresh_cache=args.refresh_cache,
    )


if __name__ == "__main__":
    main()
