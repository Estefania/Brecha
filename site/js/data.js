const DATA_DIR = "../data/site";

async function fetchJson(name) {
  const res = await fetch(`${DATA_DIR}/${name}`);
  if (!res.ok) throw new Error(`Could not load ${name}: ${res.status}`);
  return res.json();
}

export async function loadAll() {
  const [distritosGeo, barriosGeo, districts, barrios, postalCodes, meta] = await Promise.all([
    fetchJson("distritos.geojson"),
    fetchJson("barrios.geojson"),
    fetchJson("districts.json"),
    fetchJson("barrios.json"),
    fetchJson("postal_codes.json"),
    fetchJson("meta.json"),
  ]);

  const districtsByCode = new Map(districts.map((d) => [d.district_code, d]));
  const barriosByCode = new Map(barrios.map((b) => [b.barrio_code, b]));
  const barriosByDistrict = new Map();
  for (const b of barrios) {
    if (!barriosByDistrict.has(b.district_code)) barriosByDistrict.set(b.district_code, []);
    barriosByDistrict.get(b.district_code).push(b);
  }

  return {
    distritosGeo, barriosGeo, districts, barrios, postalCodes, meta,
    districtsByCode, barriosByCode, barriosByDistrict,
  };
}
