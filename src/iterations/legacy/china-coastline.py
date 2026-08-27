# 独立脚本：仅导出中国海岸线经纬度 CSV
from pathlib import Path
import pandas as pd
import geopandas as gpd
from shapely.ops import unary_union
from paths import CHINA_SHP, COASTLINE_SHP, RESULTS_DIR

# ====================== 路径（和你原来的一样）======================
OUTPUT_CSV = RESULTS_DIR / "derived" / "china_coastline.csv"

# ====================== 提取中国海岸线 ======================
print("正在提取中国海岸线...")

# 1. 读取国界
world = gpd.read_file(CHINA_SHP)
china = world[world["NAME"].isin(["China", "Taiwan"])].unary_union

# 2. 读取海岸线并裁剪
coast = gpd.read_file(COASTLINE_SHP)
china_coast = coast[coast.intersects(china)]

# 3. 提取所有坐标点
coords = []
for geom in china_coast.geometry:
    if geom.type == "LineString":
        for lon, lat in geom.coords:
            coords.append({"lon": lon, "lat": lat})
    elif geom.type == "MultiLineString":
        for line in geom.geoms:
            for lon, lat in line.coords:
                coords.append({"lon": lon, "lat": lat})

# 4. 保存 CSV
df = pd.DataFrame(coords)
OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
df.to_csv(OUTPUT_CSV, index=False)

print(f"✅ 海岸线 CSV 已保存到：{OUTPUT_CSV}")
print(f"总点数：{len(df)}")
