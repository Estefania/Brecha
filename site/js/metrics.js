// Pure numeric helpers shared by main.js (state/coloring) and panel.js (rendering).
// No DOM access here.

export function incomeField(base) {
  return base === "persona" ? "net_income_person" : "net_income_household";
}

// Income value for a district (from districts.json's timeseries) or a barrio
// (from barrios.json's income series), for a given year/base.
function incomeValueReal(level, record, base, year) {
  const field = incomeField(base);
  if (level === "district") return record?.timeseries?.[year]?.[field] ?? null;
  return record?.income?.[year]?.[field] ?? null;
}

// --- Projection (slider map only) -------------------------------------------------
// Income (real to 2023) and rent (real to 2024) are extended to MAX_PROJECTION_YEAR so
// the year slider can reach 2025, the latest year purchase prices exist. Same method as
// the index chart's extrapolateForward(): average annual growth over the last (up to)
// 3 real intervals of THAT AREA'S OWN series, compounded forward. Never applied to
// purchase price (real-only), never fills a gap in the middle of a series, and never
// reaches more than MAX_PROJECTION_GAP years past an area's last real point.
// The index chart deliberately keeps using the *Real functions below, so projected
// numbers never sneak into the "real series" part of a chart line.
export const MAX_PROJECTION_YEAR = 2025;
const MAX_PROJECTION_GAP = 3;
const projectionCache = new WeakMap();

function realOrProjected(record, key, realFn, year) {
  const real = realFn(year);
  if (real != null) return { value: real, projected: false };
  if (!record || year > MAX_PROJECTION_YEAR) return { value: null, projected: false };
  let byKey = projectionCache.get(record);
  if (!byKey) { byKey = new Map(); projectionCache.set(record, byKey); }
  let info = byKey.get(key);
  if (!info) {
    const ys = [], vs = [];
    for (let y = 2011; y <= MAX_PROJECTION_YEAR; y++) {
      const v = realFn(y);
      if (v != null) { ys.push(y); vs.push(v); }
    }
    let rate = null;
    if (ys.length >= 2) {
      const start = Math.max(0, ys.length - 1 - 3);
      const rates = [];
      for (let i = start; i < ys.length - 1; i++) {
        if (vs[i] > 0) rates.push(Math.pow(vs[i + 1] / vs[i], 1 / (ys[i + 1] - ys[i])) - 1);
      }
      if (rates.length) rate = rates.reduce((a, b) => a + b, 0) / rates.length;
    }
    info = { lastYear: ys[ys.length - 1], lastValue: vs[vs.length - 1], rate };
    byKey.set(key, info);
  }
  if (info.rate == null || year <= info.lastYear || year - info.lastYear > MAX_PROJECTION_GAP) return { value: null, projected: false };
  return { value: info.lastValue * Math.pow(1 + info.rate, year - info.lastYear), projected: true };
}

export function incomeValue(level, record, base, year) {
  return realOrProjected(record, `inc:${base}`, (y) => incomeValueReal(level, record, base, y), year).value;
}

// kind: "renta" or "alquiler" (the only two metrics that are ever projected).
export function isProjected(kind, level, record, base, year) {
  if (kind === "renta") return realOrProjected(record, `inc:${base}`, (y) => incomeValueReal(level, record, base, y), year).projected;
  if (kind === "alquiler") return realOrProjected(record, "rent", (y) => priceValueReal(level, record, "alquiler", y), year).projected;
  return false;
}

// Price value for "alquiler" (rent_m2, follows the slider year at both levels),
// "compra_nueva"/"compra_usada" (the two purchase series by home type, both real Colegio de
// Registradores transactions, official at district AND barrio level), or "compra" (the TOTAL
// price of all sales, used by the map layer/cross toggle and the effort card, which show one
// number by design - see panel.js for nueva/usada split out as separate rows/lines). Both
// district and barrio follow the slider year.
export function priceValue(level, record, kind, year) {
  if (kind === "alquiler") return realOrProjected(record, "rent", (y) => priceValueReal(level, record, "alquiler", y), year).value;
  return priceValueReal(level, record, kind, year);
}

function priceValueReal(level, record, kind, year) {
  // ASKING rent of new listings (Idealista via the Ayuntamiento, pipeline/09_rent_asking.py):
  // district level only, never projected - the counterpart of SERPAVI's contracts-in-force "alquiler".
  if (kind === "alquiler_oferta") {
    return level === "district" ? record?.timeseries?.[year]?.rent_asking_m2 ?? null : null;
  }
  if (kind === "alquiler") {
    if (level === "district") return record?.timeseries?.[year]?.rent_m2 ?? null;
    return record?.rent?.[year]?.rent_m2 ?? null;
  }
  if (kind === "compra_nueva") {
    if (level === "district") return record?.timeseries?.[year]?.price_m2_new ?? null;
    return record?.purchase?.[year]?.price_m2_new ?? null;
  }
  if (kind === "compra_usada") {
    if (level === "district") return record?.timeseries?.[year]?.price_m2_used ?? null;
    return record?.purchase?.[year]?.price_m2_used ?? null;
  }
  // kind === "compra": the TOTAL price (all sales, new + used weighted by real volume) - the
  // registry's own total at both levels. (It used to be a simple average of nueva and usada,
  // which overstated prices - new-build is a small share of sales - and silently changed
  // meaning when "nueva" was blank.)
  if (level === "district") return record?.timeseries?.[year]?.price_m2_total ?? null;
  return record?.purchase?.[year]?.price_m2_total ?? null;
}

export function cityAverage(records, valueFn) {
  const values = records.map(valueFn).filter((v) => v != null && !Number.isNaN(v));
  if (!values.length) return null;
  return values.reduce((a, b) => a + b, 0) / values.length;
}

export function pctDelta(value, reference) {
  if (value == null || reference == null || reference === 0) return null;
  return ((value - reference) / reference) * 100;
}

// The "Esfuerzo" map layer and compare mode both use these fixed reference sizes, so the
// map, its legend and the compare view always talk about the same home.
export const EFFORT_M2 = { alquiler: 60, compra: 80 };
// FIXED (not data-quantile) class edges: each colour means the same effort in every year and
// area. Rent: % of annual household income for 60 m2 (30% is the usual "heavy burden"
// reference); buy: years of full income for 80 m2. Chosen from the real 2015-2023 distribution
// (rent mostly 15-25%, buy mostly 4-8 years).
// Per-person income is ~2.4-2.6x lower than household income (avg household ~2.6 people), so
// the same edges would paint every area the darkest class: "persona" gets its own edges,
// scaled to its real distribution (rent 35-65% of a person's income, buy 10-20 years).
export const EFFORT_BREAKS = {
  hogar: { alquiler: [15, 20, 25, 30], compra: [4, 6, 8, 10] },
  persona: { alquiler: [35, 45, 55, 65], compra: [10, 13, 16, 20] },
};

// Effort of one area/year for the given cross ("alquiler" -> rent %, "compra" -> years to buy),
// at EFFORT_M2. Uses projection-aware income/rent (see isProjected), null if either is missing.
// kind: any price kind - "alquiler" (contracts in force), "alquiler_oferta" (asking rent, district
// only), "compra" (total), "compra_nueva", "compra_usada". Rent kinds give % of annual income for
// EFFORT_M2.alquiler m2, purchase kinds give years of income for EFFORT_M2.compra m2. Uses
// projection-aware income/rent (see isProjected), null if either is missing.
export function effortAt(level, record, base, kind, year) {
  const income = incomeValue(level, record, base, year);
  const price = priceValue(level, record, kind, year);
  return effortFamily(kind) === "compra"
    ? buyEffortYears(price, EFFORT_M2.compra, income)
    : rentEffortPct(price, EFFORT_M2.alquiler, income);
}

export function effortFamily(kind) {
  return kind.startsWith("compra") ? "compra" : "alquiler";
}

// The price kind the MAP uses for "alquiler"/"compra" given the user's two source choices.
// rentSource: "contratos" | "oferta" (oferta exists only at district level, so any other level
// falls back to contratos); compraType: "total" | "nueva" | "usada". Anything else passes through.
export function activePriceKind(name, level, rentSource, compraType) {
  if (name === "alquiler") return level === "district" && rentSource === "oferta" ? "alquiler_oferta" : "alquiler";
  if (name === "compra") return compraType === "nueva" ? "compra_nueva" : compraType === "usada" ? "compra_usada" : "compra";
  return name;
}

// Rent effort: % of annual income spent renting `m2` square metres for a year.
export function rentEffortPct(rentM2Price, m2, annualIncome) {
  if (rentM2Price == null || annualIncome == null || annualIncome === 0) return null;
  const annualRent = rentM2Price * m2 * 12;
  return (annualRent / annualIncome) * 100;
}

// Buy effort: years of full annual income needed to buy `m2` square metres.
export function buyEffortYears(priceM2, m2, annualIncome) {
  if (priceM2 == null || annualIncome == null || annualIncome === 0) return null;
  return (priceM2 * m2) / annualIncome;
}

// One real index series (100 = each line's OWN first real year) for a single value
// function, as far as its own real data goes. Two independences, not one: (a) a
// metric with more recent real data than another (e.g. rent through 2024 vs income
// through 2023) must not be held back just because a DIFFERENT metric runs out
// sooner - each line shows everything real it actually has, and extrapolateForward()
// picks up separately from each line's own end; (b) a metric that STARTS later than
// the others (barrio purchase price has zero barrios with data in 2015, the
// earliest year income/rent offer) must not blank out the whole chart just because
// `years[0]` isn't its own first real year - each line finds its own earliest real
// year and indexes FROM there, rather than requiring a globally shared base year.
// An occasional missing YEAR IN THE MIDDLE (a barrio with thin coverage some year)
// is skipped rather than truncating the whole series there, same tolerance the rest
// of this pipeline already has for blank sections/years.
function realSeries(valueFn, years) {
  const baseIdx = years.findIndex((y) => valueFn(y) != null);
  if (baseIdx === -1) return null;
  const base0 = valueFn(years[baseIdx]);
  const outYears = [];
  const outIdx = [];
  const outVals = [];
  for (let i = baseIdx; i < years.length; i++) {
    const v = valueFn(years[i]);
    if (v == null) continue;
    outYears.push(years[i]);
    outIdx.push((v / base0) * 100);
    outVals.push(v);
  }
  return outYears.length >= 2 ? { years: outYears, idx: outIdx, vals: outVals } : null;
}

// {income: {years, idx}, priceSeries: [{kind, years, idx}, ...]} for the index chart,
// 2015 = 100. priceKinds is an array (usually ["alquiler"], or ["compra_nueva",
// "compra_usada"] when cross=compra, so the two methodologically-different purchase
// series each get their own line instead of being averaged into one). Each line's
// `years`/`idx` can have a DIFFERENT length - they are independent series sharing
// only the same base year, not a single shared x-axis (see realSeries() above).
// A price kind with fewer than 2 real points (e.g. "compra_nueva" in most Retiro
// barrios - too few new-build sales to clear the 15-transaction secrecy threshold) is
// dropped from `priceSeries` and listed in `missingKinds`, rather than making the whole
// chart return null - the income line and any other price line that DO have data are
// still worth showing. Returns null only when income is missing or NO price kind has data.
export function indexSeries(level, record, base, priceKinds, years) {
  const income = realSeries((y) => incomeValueReal(level, record, base, y), years);
  const all = priceKinds.map((kind) => ({ kind, series: realSeries((y) => priceValueReal(level, record, kind, y), years) }));
  const priceSeries = all.filter((p) => p.series).map((p) => ({ kind: p.kind, ...p.series }));
  const missingKinds = all.filter((p) => !p.series).map((p) => p.kind);
  if (!income || !priceSeries.length) return null;
  return { income, priceSeries, missingKinds };
}

// Extends an index series (2015=100 style) forward from its last REAL year to
// `currentYear`, using the average annual growth rate over the last (up to) 3 real
// intervals, compounded forward. This is a projection, not real data - the caller
// (panel.js) must render it as visually distinct (dashed, muted) and label it as
// such; it must never be mixed into the real `years`/`idx` arrays this returns from.
// Returns {extYears, extIdx} STARTING at the last real year/value (so a line drawn
// from the real segment's end connects seamlessly), or empty arrays if there's
// nothing to extrapolate (already at/past currentYear, or too little data).
export function extrapolateForward(years, idx, currentYear) {
  const lastYear = years[years.length - 1];
  if (lastYear >= currentYear || years.length < 2) return { extYears: [], extIdx: [] };
  const lookback = Math.min(3, years.length - 1);
  const startAt = years.length - 1 - lookback;
  const rates = [];
  for (let i = startAt; i < years.length - 1; i++) {
    if (idx[i] > 0) rates.push(idx[i + 1] / idx[i] - 1);
  }
  if (!rates.length) return { extYears: [], extIdx: [] };
  const avgRate = rates.reduce((a, b) => a + b, 0) / rates.length;
  const extYears = [lastYear];
  const extIdx = [idx[idx.length - 1]];
  let year = lastYear;
  let value = idx[idx.length - 1];
  while (year < currentYear) {
    year += 1;
    value *= 1 + avgRate;
    extYears.push(year);
    extIdx.push(value);
  }
  return { extYears, extIdx };
}

export function rankOf(code, entries, valueFn) {
  const ranked = entries
    .map((e) => ({ code: e.code, value: valueFn(e) }))
    .filter((e) => e.value != null)
    .sort((a, b) => b.value - a.value);
  const idx = ranked.findIndex((e) => e.code === code);
  return idx === -1 ? null : { rank: idx + 1, total: ranked.length };
}
