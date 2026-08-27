"""项目内统一的目录定义。

所有可执行脚本都从这里获取输入、底图和输出路径，避免依赖根目录的临时链接。
"""
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

AIS_DATA_DIR = PROJECT_ROOT / "data" / "ais" / "cleaned" / "data"
REFERENCE_DIR = PROJECT_ROOT / "data" / "reference" / "实际数据"
GEOSPATIAL_DIR = PROJECT_ROOT / "data" / "geospatial"
COASTLINE_SHP = GEOSPATIAL_DIR / "ne_10m_coastline" / "ne_10m_coastline.shp"
CHINA_SHP = (
    GEOSPATIAL_DIR
    / "ne_10m_admin_0_countries"
    / "ne_10m_admin_0_countries.shp"
)

RESULTS_DIR = PROJECT_ROOT / "results"
ITERATION_RESULTS_DIR = RESULTS_DIR / "iterations"


def numbered_result_dirs() -> list[Path]:
    """返回按数字排序的正式结果目录，缓存和说明文件不参与编号。"""
    if not RESULTS_DIR.exists():
        return []
    return sorted(
        (path for path in RESULTS_DIR.iterdir() if path.is_dir() and path.name.isdigit()),
        key=lambda path: int(path.name),
    )


def latest_result_dir() -> Path:
    versions = numbered_result_dirs()
    if not versions:
        raise FileNotFoundError("results/ 下还没有编号结果目录")
    return versions[-1]


def next_result_dir() -> Path:
    versions = numbered_result_dirs()
    number = int(versions[-1].name) + 1 if versions else 1
    return RESULTS_DIR / f"{number:02d}"


def iteration_result_dir(iteration_name: str) -> Path:
    """返回某一参数迭代唯一对应的结果目录。"""
    if not iteration_name or Path(iteration_name).name != iteration_name:
        raise ValueError(f"无效的迭代名称：{iteration_name!r}")
    return ITERATION_RESULTS_DIR / iteration_name
