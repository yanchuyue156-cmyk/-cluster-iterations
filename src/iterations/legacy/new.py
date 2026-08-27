from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import pandas as pd
import numpy as np
import geopandas as gpd
from sklearn.cluster import DBSCAN
import utm
from shapely.geometry import Point
from shapely.ops import unary_union
from paths import AIS_DATA_DIR, CHINA_SHP, COASTLINE_SHP, CURRENT_RESULTS_DIR

print("程序开始运行（按你的要求定制版）")

# =========================
# 基础路径
# =========================
OUTPUT_DIR = CURRENT_RESULTS_DIR
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# =========================
# 列名 & 参数（全部保持你原来的）
# =========================
USE_COLS = [
    "MMSI","BaseDateTime","Latitude","Longitude","SOG","COG","Heading",
    "Status","ShipName","DataType","utc","datetime"
]
DTYPE_MAP = {"MMSI": "int64", "Latitude": "float64", "Longitude": "float64"}

STOP_SPEED_KN = 1
MIN_STOP_MINUTES = 60
BERTH_DRIFT_MAX = 150
ANCH_DRIFT_MIN = 300
ANCH_DURATION_MIN = 24 * 60

BERTH_EPS = 150
BERTH_MIN_SAMPLES = 2
ANCH_EPS = 6000
ANCH_MIN_SAMPLES = 5
PORT_EPS = 1000
PORT_MIN_SAMPLES = 1

BERTH_COAST_MAX = 7500
ANCH_COAST_MIN = 2000
ANCH_COAST_MAX = 20000

CHINA_LON_MIN = 73
CHINA_LON_MAX = 135
CHINA_LAT_MIN = 18
CHINA_LAT_MAX = 54

# =========================
# 工具函数
# =========================
def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2)**2 + np.cos(lat1)*np.cos(lat2)*np.sin(dlon/2)**2
    return 2 * R * np.arctan2(np.sqrt(a), np.sqrt(1-a))

def to_utm(lat, lon):
    return utm.from_latlon(lat, lon)[:2]

# =========================
# 【你的要求 1】使用你原来的海岸线 shp → 点转线 → 精准距离
# =========================
def get_china_coastline_line():
    coast = gpd.read_file(COASTLINE_SHP)
    world = gpd.read_file(CHINA_SHP)
    china = world[world["NAME"].isin(["China", "Taiwan"])].unary_union
    china_coast = coast[coast.intersects(china)]
    return china_coast.to_crs(3857).unary_union

def add_real_coast_distance(df, coast_line_3857):
    print("🌊 计算到海岸线真实距离（点→线）")
    if len(df) == 0:
        return df
    gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat), crs=4326).to_crs(3857)
    gdf["distance_to_coast"] = gdf.geometry.distance(coast_line_3857)
    return pd.DataFrame(gdf.drop(columns="geometry"))

# =========================
# 【你的要求 2】泊位：保持四四方方（不变）
# =========================
def cluster_to_rectangle(df_clustered, output_type):
    results = []
    if df_clustered.empty:
        return pd.DataFrame()
    for cid, g in df_clustered.groupby("cluster"):
        if cid == -1: continue
        clat, clon = g.lat.mean(), g.lon.mean()
        min_lon, max_lon = g.lon.min(), g.lon.max()
        min_lat, max_lat = g.lat.min(), g.lat.max()
        poly = f"POLYGON(({min_lon} {min_lat}, {max_lon} {min_lat}, {max_lon} {max_lat}, {min_lon} {max_lat}, {min_lon} {min_lat}))"
        results.append({
            "cluster_id": cid, "lat": clat, "lon": clon, "count": len(g),
            "type": output_type, "polygon": poly
        })
    return pd.DataFrame(results)

# =========================
# 【升级】锚地：真实凸包轮廓
# =========================
def cluster_to_convex_hull(df_clustered, output_type):
    results = []
    if df_clustered.empty:
        return pd.DataFrame()
    for cid, g in df_clustered.groupby("cluster"):
        if cid == -1: continue
        pts = [Point(lon, lat) for lon, lat in zip(g.lon, g.lat)]
        hull = unary_union(pts).convex_hull
        results.append({
            "cluster_id": cid, "lat": g.lat.mean(), "lon": g.lon.mean(),
            "count": len(g), "type": output_type, "polygon": hull.wkt
        })
    return pd.DataFrame(results)

# =========================
# 【升级】港口：真实凸包轮廓
# =========================
def build_ports(berths):
    print("🏭 港口聚类（真实轮廓）")
    if berths.empty:
        return pd.DataFrame()
    b = berths.copy()
    b[["x","y"]] = b.apply(lambda r: pd.Series(to_utm(r.lat, r.lon)), axis=1)
    b["port_id"] = DBSCAN(eps=PORT_EPS, min_samples=PORT_MIN_SAMPLES).fit_predict(b[["x","y"]])
    ports = []
    for pid, g in b[b.port_id != -1].groupby("port_id"):
        pts = [Point(lon, lat) for lon, lat in zip(g.lon, g.lat)]
        hull = unary_union(pts).convex_hull
        ports.append({
            "port_id": pid, "lat": g.lat.mean(), "lon": g.lon.mean(),
            "berth_count": len(g), "polygon": hull.wkt
        })
    return pd.DataFrame(ports)

# =========================
# 以下全部保持你原来的代码不动
# =========================
def read_ship_csv(path):
    for e in ["utf-8","gbk","latin1"]:
        try: return pd.read_csv(path, usecols=USE_COLS, dtype=DTYPE_MAP, encoding=e)
        except: continue
    raise RuntimeError(f"读取失败 {path}")

def load_all_ships_data():
    folder = AIS_DATA_DIR
    files = list(folder.glob("*.csv"))
    df_list = []
    with ThreadPoolExecutor(min(8, len(files))) as exe:
        fut = [exe.submit(read_ship_csv, f) for f in files]
        for i,f in enumerate(as_completed(fut),1):
            df_list.append(f.result())
            print(f"✔ {i}/{len(fut)}")
    df = pd.concat(df_list, ignore_index=True)
    print("AIS总量:", len(df))
    return df

def prepare_ship_data(df):
    df = df.rename(columns={"BaseDateTime":"timestamp","Latitude":"lat","Longitude":"lon"})
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df.sort_values(["MMSI","timestamp"])

def detect_stops(df):
    gb = df.groupby("MMSI")
    df["lat_prev"] = gb["lat"].shift(1)
    df["lon_prev"] = gb["lon"].shift(1)
    df["time_prev"] = gb["timestamp"].shift(1)
    df["time_diff"] = (df["timestamp"] - df["time_prev"]).dt.total_seconds()
    df["distance"] = haversine(df["lat"],df["lon"],df["lat_prev"],df["lon_prev"])
    df["speed_kn"] = (df["distance"] / df["time_diff"]) * 1.94384
    df["speed_kn"] = df["speed_kn"].replace([np.inf,-np.inf],0).fillna(0)
    df["stop"] = (df["speed_kn"] < STOP_SPEED_KN).astype(int)
    df["stop_group"] = gb["stop"].transform(lambda x: (x!=x.shift(1)).cumsum())

    stops = df[df["stop"]==1].groupby(["MMSI","stop_group"]).agg(
        lat=("lat","mean"), lon=("lon","mean"),
        start=("timestamp","min"), end=("timestamp","max"),
        lat_min=("lat","min"), lat_max=("lat","max"),
        lon_min=("lon","min"), lon_max=("lon","max")
    )
    stops["duration"] = (stops["end"] - stops["start"]).dt.total_seconds()/60
    stops["drift"] = haversine(stops["lat_min"],stops["lon_min"],stops["lat_max"],stops["lon_max"])
    stops = stops[stops["duration"]>=MIN_STOP_MINUTES].reset_index()
    print("有效停泊段:", len(stops))
    return stops

def classify_behavior(stops):
    stops = stops.copy()
    stops["behavior"] = "unknown"
    stops.loc[stops["drift"] < BERTH_DRIFT_MAX, "behavior"] = "berth_like"
    stops.loc[(stops["drift"]>=ANCH_DRIFT_MIN)&(stops["duration"]>=ANCH_DURATION_MIN), "behavior"] = "anchorage_like"
    return stops

def run_dbscan(df_input, eps, min_samples):
    if df_input.empty: return pd.DataFrame()
    dfin = df_input.copy()
    dfin[["x","y"]] = dfin.apply(lambda r: pd.Series(to_utm(r.lat, r.lon)), axis=1)
    dfin["cluster"] = DBSCAN(eps=eps, min_samples=min_samples).fit_predict(dfin[["x","y"]])
    return dfin

def add_land_flag(df):
    if df.empty: return df
    world = gpd.read_file(CHINA_SHP)
    china = world[world["NAME"].isin(["China","Taiwan"])].to_crs(3857).unary_union
    gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat), crs=4326).to_crs(3857)
    gdf["inside_china_land"] = gdf.geometry.within(china)
    return pd.DataFrame(gdf.drop(columns="geometry"))

def filter_berths(berths):
    coastal = berths[berths["distance_to_coast"] <= BERTH_COAST_MAX]
    inland = berths[(berths["distance_to_coast"]>BERTH_COAST_MAX)&(berths["inside_china_land"]==True)]
    return pd.concat([coastal,inland], ignore_index=True)

def filter_anchorages(anchorages):
    return anchorages[(anchorages["distance_to_coast"]>=ANCH_COAST_MIN)&(anchorages["distance_to_coast"]<=ANCH_COAST_MAX)].copy()

def filter_china(df):
    if df.empty: return df
    return df[(df.lon>=73)&(df.lon<=135)&(df.lat>=18)&(df.lat<=54)].copy()

def export_csv(berths, anchorages, ports):
    berths.to_csv(OUTPUT_DIR/"china_berths.csv", index=False)
    anchorages.to_csv(OUTPUT_DIR/"china_anchorages.csv", index=False)
    ports.to_csv(OUTPUT_DIR/"china_ports.csv", index=False)
    print("✅ 导出完成")

# =========================
# 主程序
# =========================
def run():
    coast_line = get_china_coastline_line()
    df = load_all_ships_data()
    df = prepare_ship_data(df)
    stops = detect_stops(df)
    stops = classify_behavior(stops)

    # 泊位：保持矩形（你要求的）
    b_cluster = run_dbscan(stops[stops.behavior=="berth_like"], BERTH_EPS, BERTH_MIN_SAMPLES)
    berths = cluster_to_rectangle(b_cluster, "berth")

    # 锚地：真实轮廓
    a_cluster = run_dbscan(stops[stops.behavior=="anchorage_like"], ANCH_EPS, ANCH_MIN_SAMPLES)
    anchorages = cluster_to_convex_hull(a_cluster, "anchorage")

    # 精准距离
    berths = add_real_coast_distance(berths, coast_line)
    anchorages = add_real_coast_distance(anchorages, coast_line)
    berths = add_land_flag(berths)

    berths = filter_berths(berths)
    anchorages = filter_anchorages(anchorages)

    # 港口：真实轮廓
    ports = build_ports(berths)

    # 中国范围过滤
    berths = filter_china(berths)
    anchorages = filter_china(anchorages)
    ports = filter_china(ports)

    print("\n===== 最终结果 =====")
    print("泊位（矩形）：", len(berths))
    print("锚地（真实轮廓）：", len(anchorages))
    print("港口（真实轮廓）：", len(ports))

    export_csv(berths, anchorages, ports)

if __name__ == "__main__":
    run()
