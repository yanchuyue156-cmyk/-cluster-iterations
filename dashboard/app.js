const map = L.map("map", { zoomControl: false }).setView([35.5, 108], 4);
L.control.zoom({ position: "topright" }).addTo(map);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "© OpenStreetMap contributors",
}).addTo(map);

const styles = {
  berths: { color: "#218db9", weight: 1, fillColor: "#37b4e6", fillOpacity: 0.35 },
  anchorages: { color: "#de7435", weight: 1.5, fillColor: "#ff9e52", fillOpacity: 0.32 },
  terminals: { color: "#9b45c7", weight: 2, fillColor: "#d578ff", fillOpacity: 0.16 },
  referenceBerths: { color: "#218c45", weight: 1, fillColor: "#67d48b", fillOpacity: 0.16, dashArray: "3 3" },
  referenceAnchorages: { color: "#9d9200", weight: 1.5, fillColor: "#f3e85c", fillOpacity: 0.14, dashArray: "5 4" },
  chinaLand: { color: "#435c70", weight: 1, fillColor: "#d9e2dd", fillOpacity: 0.72 },
  chinaCoast: { color: "#28475d", weight: 1.4, opacity: 0.9 },
};

function popup(properties, title) {
  const rows = Object.entries(properties)
    .filter(([, value]) => value !== null && value !== undefined && value !== "")
    .map(([key, value]) => `<p class="popup-row"><b>${key}</b>：${value}</p>`)
    .join("");
  return `<p class="popup-title">${title}</p>${rows}`;
}

async function loadData(key, path) {
  if (window.DASHBOARD_DATA) return window.DASHBOARD_DATA[key];
  const response = await fetch(path);
  if (!response.ok) throw new Error(`无法读取 ${path}`);
  return response.json();
}

async function geojson(key, path, title, style) {
  const data = await loadData(key, path);
  return L.geoJSON(data, {
    style,
    onEachFeature: (feature, layer) => layer.bindPopup(popup(feature.properties, title)),
  });
}

async function initialize() {
  const [summary, berths, anchorages, terminals, referenceBerths, referenceAnchorages, chinaLand, chinaCoast] = await Promise.all([
    loadData("summary", "data/summary.json"),
    geojson("berths", "data/berths.geojson", "预测泊位", styles.berths),
    geojson("anchorages", "data/anchorages.geojson", "预测锚地", styles.anchorages),
    geojson("terminals", "data/terminals.geojson", "预测码头", styles.terminals),
    geojson("referenceBerths", "data/reference_berths.geojson", "真实码头", styles.referenceBerths),
    geojson("referenceAnchorages", "data/reference_anchorages.geojson", "真实锚地", styles.referenceAnchorages),
    geojson("chinaLand", "data/china_land.geojson", "中国陆地区域", styles.chinaLand),
    geojson("chinaCoast", "data/china_coast.geojson", "中国海岸线", styles.chinaCoast),
  ]);

  const values = {
    "predicted-berths": summary.predicted_berths,
    "predicted-anchorages": summary.predicted_anchorages,
    "predicted-terminals": summary.predicted_terminals,
    "reference-berths": summary.reference_berths,
    "reference-anchorages": summary.reference_anchorages,
  };
  Object.entries(values).forEach(([id, value]) => { document.getElementById(id).textContent = Number(value).toLocaleString(); });
  document.getElementById("generated-at").textContent = `结果版本：${summary.result_version} · 数据导出时间：${summary.generated_at}`;

  chinaLand.addTo(map);
  chinaCoast.addTo(map);
  berths.addTo(map);
  anchorages.addTo(map);
  terminals.addTo(map);
  L.control.layers(null, {
    "中国陆地区域": chinaLand,
    "中国海岸线": chinaCoast,
    "预测泊位": berths,
    "预测锚地": anchorages,
    "预测码头": terminals,
    "真实码头": referenceBerths,
    "真实锚地": referenceAnchorages,
  }, { collapsed: false, position: "topright" }).addTo(map);

  if (chinaLand.getBounds().isValid()) map.fitBounds(chinaLand.getBounds(), { padding: [24, 24] });
}

initialize().catch((error) => {
  console.error(error);
  document.querySelector(".hint").textContent = `看板数据加载失败：${error.message}`;
});
