#!/usr/bin/env bash
# 将外部保存的 AIS CSV 复制到本项目的标准输入位置。
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "用法: $0 /path/to/ais-source" >&2
  echo "源目录应直接包含 CSV，或包含 cleaned/data/ 目录。" >&2
  exit 2
fi

source_dir=$1
if [[ ! -d "$source_dir" ]]; then
  echo "找不到 AIS 源目录: $source_dir" >&2
  exit 1
fi

if [[ -d "$source_dir/cleaned/data" ]]; then
  source_dir="$source_dir/cleaned/data"
fi

if ! find "$source_dir" -maxdepth 1 -type f -name '*.csv' -print -quit | grep -q .; then
  echo "源目录中没有找到 CSV: $source_dir" >&2
  exit 1
fi

target_dir="$(cd "$(dirname "$0")/.." && pwd)/data/ais/cleaned/data"
mkdir -p "$target_dir"
rsync -a --info=progress2 "$source_dir/" "$target_dir/"

echo "AIS 数据已复制到: $target_dir"
