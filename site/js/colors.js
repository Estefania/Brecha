// Palette from the design mockup (Brecha Madrid — visualizador de desigualdad.html).
export const INCOME_RAMP = ["#DCE7F0", "#8FB0CF", "#2F5D8C"];
export const PRICE_RAMP = ["#F0E2CE", "#E5A56B", "#B4560F"];
// Single-hue (orange) 5-class ramp for the "Esfuerzo" layer: light = little effort, dark = a lot.
export const EFFORT_RAMP = ["#F6EAD8", "#F0CFA0", "#E5A56B", "#D9822B", "#B4560F"];
export const DIVERGING = ["#2F5D8C", "#8FB0CF", "#E8E4DB", "#E5A56B", "#B4560F"];
export const NO_DATA_COLOR = "#E4DED0";

// income tercile (0-2) + price tercile (0-2) -> one of 9 cells
export const BIVARIATE_GRID = {
  "00": "#E8E4DB", "10": "#B4CBDD", "20": "#7FA3C7",
  "01": "#E5BE8C", "11": "#B7B0A6", "21": "#7C8FAE",
  "02": "#D9822B", "12": "#B08663", "22": "#4E5C78",
};
// cells dark enough to need white text/labels on top
export const DARK_CELLS = new Set(["#4E5C78", "#2F5D8C", "#B4560F"]);

function quantileBreaks(values, k) {
  const sorted = values.filter((v) => v != null && !Number.isNaN(v)).sort((a, b) => a - b);
  if (sorted.length === 0) return Array(k - 1).fill(0);
  const q = (p) => sorted[Math.min(sorted.length - 1, Math.floor(p * sorted.length))];
  const breaks = [];
  for (let i = 1; i < k; i++) breaks.push(q(i / k));
  return breaks;
}

function bucketOf(value, breaks) {
  if (value == null || Number.isNaN(value)) return null;
  for (let i = 0; i < breaks.length; i++) if (value <= breaks[i]) return i;
  return breaks.length;
}

// Two breakpoints splitting `values` into three roughly-equal groups (terciles).
export function terciles(values) {
  return quantileBreaks(values, 3);
}

export function bucketIndex(value, breakpoints) {
  return bucketOf(value, breakpoints);
}

export function colorForValue(value, breakpoints, ramp = INCOME_RAMP) {
  const idx = bucketOf(value, breakpoints);
  return idx == null ? NO_DATA_COLOR : ramp[idx];
}

export function classIndex(value, breakpoints) {
  return bucketOf(value, breakpoints);
}

export function bivariateColor(incomeValue, priceValue, incomeBreaks, priceBreaks) {
  const i = bucketOf(incomeValue, incomeBreaks);
  const p = bucketOf(priceValue, priceBreaks);
  if (i == null || p == null) return NO_DATA_COLOR;
  return BIVARIATE_GRID[`${i}${p}`];
}

export function divergingColor(delta, breaks) {
  const idx = bucketOf(delta, breaks);
  return idx == null ? NO_DATA_COLOR : DIVERGING[idx];
}

export function textColorFor(fill) {
  return DARK_CELLS.has(fill) ? "#FFFFFF" : "#1C1B18";
}
