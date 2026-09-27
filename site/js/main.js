import { loadAll } from "./data.js";
import { terciles, colorForValue, classIndex, bivariateColor, divergingColor, INCOME_RAMP, PRICE_RAMP, EFFORT_RAMP, DIVERGING, BIVARIATE_GRID } from "./colors.js";
import { renderMap } from "./map.js";
import { renderPanel } from "./panel.js";
import { incomeValue, priceValue, isProjected, effortAt, effortFamily, activePriceKind, EFFORT_M2, EFFORT_BREAKS, MAX_PROJECTION_YEAR, rentEffortPct, buyEffortYears } from "./metrics.js";

const euro = new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
const euroM2 = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 2 });
const deltaPct = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 1, signDisplay: "always" });

const svg = d3.select("#map");
const panelContainer = document.getElementById("panel-content");
const layerButtons = document.getElementById("layer-buttons");
const crossSection = document.getElementById("cross-section");
const crossButtons = document.getElementById("cross-buttons");
const priceSourceSection = document.getElementById("price-source-section");
const priceSourceLabel = document.getElementById("price-source-label");
const priceSourceButtons = document.getElementById("price-source-buttons");
const priceSourceNote = document.getElementById("price-source-note");
const baseButtons = document.getElementById("base-buttons");
const baseNote = document.getElementById("base-note");
const legendGridWrap = document.getElementById("legend-grid-wrap");
const legendGrid = document.getElementById("legend-grid");
const legendAxisLabel = document.getElementById("legend-axis-label");
const legendStripWrap = document.getElementById("legend-strip-wrap");
const legendStrip = document.getElementById("legend-strip");
const stripLeftEl = document.getElementById("strip-left");
const stripRightEl = document.getElementById("strip-right");
const legendNote = document.getElementById("legend-note");
const crumbMadrid = document.getElementById("crumb-madrid");
const crumbDistrictWrap = document.getElementById("crumb-district-wrap");
const crumbDistrict = document.getElementById("crumb-district");
const mapHint = document.getElementById("map-hint");
const yearSlider = document.getElementById("year-slider");
const yearReadout = document.getElementById("year-readout");
const yearProjNote = document.getElementById("year-proj-note");
const yearTicks = document.getElementById("year-ticks");
const playBtn = document.getElementById("play-btn");
const compareBtn = document.getElementById("compare-btn");
const searchInput = document.getElementById("search-input");
const searchBtn = document.getElementById("search-btn");
const searchResults = document.getElementById("search-results");

const LAYERS = [["esfuerzo", "Esfuerzo"], ["cruce", "Cruce"], ["renta", "Renta"], ["alquiler", "Alquiler"], ["compra", "Compra"]];
const CROSSES = [["alquiler", "Alquiler"], ["compra", "Compra"]];
const RENT_SOURCES = [["contratos", "Contratos en vigor"], ["oferta", "Precio de oferta"]];
const COMPRA_TYPES = [["total", "Total"], ["nueva", "Obra nueva"], ["usada", "Segunda mano"]];
const BASES = [["hogar", "Hogar"], ["persona", "Persona"]];

async function main() {
  const data = await loadAll();
  // Years with real data for all three metrics (district level) - the default view.
  const realYears = data.meta.years_district_all_three_metrics;
  // The slider itself extends past that, up to the latest year purchase price exists
  // (2025), with income and rent PROJECTED for the years they haven't been published
  // for yet (see metrics.js realOrProjected) and every such year flagged with "*".
  const lastPurchaseYear = Math.max(...data.meta.years_barrio_purchase, ...data.meta.years_district_income_rent);
  const lastYear = Math.min(lastPurchaseYear, MAX_PROJECTION_YEAR);
  const years = Array.from({ length: lastYear - Math.min(...realYears) + 1 }, (_, i) => Math.min(...realYears) + i);
  const lastIncomeYear = Math.max(...data.meta.years_barrio_income);
  const lastRentYear = Math.max(...data.meta.years_barrio_rent);
  const yearLabel = (y) => (y > lastIncomeYear ? `${y}*` : String(y));
  function projectionNote(y) {
    const parts = [];
    if (y > lastIncomeYear) parts.push("renta");
    if (y > lastRentYear && rentSource() === "contratos") parts.push("alquiler");
    if (!parts.length) return "";
    return `* ${parts.join(" y ")} proyectad${parts.length > 1 ? "os" : "a"} (no es dato publicado)`;
  }

  const state = {
    level: "district",
    districtCode: null,
    selectedBarrioCode: null,
    year: Math.max(...realYears),
    layer: "esfuerzo",
    cross: "alquiler",
    rentSource: "contratos",
    compraType: "total",
    base: "hogar",
    compare: false,
    rentM2: 60,
    buyM2: 80,
    playing: false,
  };
  let playTimer = null;

  yearSlider.min = String(Math.min(...years));
  yearSlider.max = String(Math.max(...years));
  yearSlider.value = String(state.year);
  function setYearUI() {
    yearReadout.textContent = yearLabel(state.year);
    const note = projectionNote(state.year);
    yearProjNote.textContent = note;
    yearProjNote.title = note;
  }
  setYearUI();
  // Tick labels are chosen from the room actually available (the slider track can be as short
  // as ~160px on a laptop, where every-other-year labels used to run together) and each is
  // placed at its true position along the track. First and last year are always shown; the
  // step is a divisor of the span so the labels stay evenly spaced (e.g. 2015..2025: every
  // year, every 2, every 5, or just the two ends).
  function renderTicks() {
    const width = yearTicks.clientWidth || 320;
    const span = years.length - 1;
    const maxLabels = Math.max(2, Math.floor(width / 36));
    const steps = Array.from({ length: span }, (_, i) => i + 1).filter((d) => span % d === 0);
    const step = steps.find((d) => span / d + 1 <= maxLabels) ?? span;
    const html = years.filter((_, i) => i % step === 0).map((y) => {
      const frac = (y - years[0]) / span;
      const edge = y === years[0] ? " tick-first" : y === years[span] ? " tick-last" : "";
      return `<span class="tick${edge}" style="left:calc(8px + ${frac} * (100% - 16px))">${yearLabel(y)}</span>`;
    }).join("");
    if (yearTicks.dataset.rendered !== html) {
      yearTicks.innerHTML = html;
      yearTicks.dataset.rendered = html;
    }
  }
  renderTicks();
  yearSlider.addEventListener("input", () => {
    state.year = Number(yearSlider.value);
    setYearUI();
    renderTicks();
    const timelineBar = document.querySelector(".timeline-bar");
    if (timelineBar) mapHint.style.bottom = `${timelineBar.offsetHeight + 36}px`;
    render();
  });

  playBtn.addEventListener("click", () => {
    state.playing = !state.playing;
    playBtn.innerHTML = state.playing
      ? `<svg width="16" height="16" viewBox="0 0 16 16" fill="#F5F1E8"><path d="M3.5 2.5h3v11h-3zM9.5 2.5h3v11h-3z"></path></svg>`
      : `<svg width="16" height="16" viewBox="0 0 16 16" fill="#F5F1E8"><path d="M4 2.5v11l9-5.5z"></path></svg>`;
    if (state.playing) {
      playTimer = setInterval(() => {
        state.year = state.year >= Math.max(...years) ? Math.min(...years) : state.year + 1;
        yearSlider.value = String(state.year);
        setYearUI();
        render();
      }, 900);
    } else {
      clearInterval(playTimer);
    }
  });

  compareBtn.addEventListener("click", () => {
    state.compare = !state.compare;
    render();
  });

  crumbMadrid.addEventListener("click", () => {
    state.level = "district";
    state.districtCode = null;
    state.selectedBarrioCode = null;
    render();
  });

  function pickLayer(layer) {
    state.layer = layer;
    if (layer === "alquiler" || layer === "compra") state.cross = layer; // alquiler/compra layer implies that cross too
    // Renta/Cruce aren't a meaningful basis for "change since 2015" (Cruce is a
    // current-snapshot bivariate view; Renta alone has nothing to compare a price
    // against) - picking either exits compare mode rather than leaving it on with a
    // now-mismatched layer button highlighted. Alquiler/Compra stay compatible with
    // compare (see effortDelta, which now follows state.cross), so picking those
    // while comparing just changes what's being compared, not whether it's active.
    if (state.compare && (layer === "renta" || layer === "cruce")) state.compare = false;
    render();
  }

  function pickCross(cross) {
    state.cross = cross;
    render();
  }

  function pickPriceSource(value) {
    if (activeFamily() === "compra") state.compraType = value;
    else state.rentSource = value;
    render();
  }

  function pickBase(base) {
    state.base = base;
    render();
  }

  function buttonGroup(container, items, activeKey, onPick, disabledKeys = new Set()) {
    container.innerHTML = items.map(([key, label]) => `<button type="button" class="toggle-btn${key === activeKey ? " active" : ""}" data-key="${key}" ${disabledKeys.has(key) ? "disabled" : ""}>${label}</button>`).join("");
    container.querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", () => onPick(btn.dataset.key));
    });
  }

  function currentEntries() {
    if (state.level === "district") {
      return data.districts.map((d) => ({ code: d.district_code, record: d }));
    }
    const barrios = data.barriosByDistrict.get(state.districtCode) || [];
    return barrios.map((b) => ({ code: b.barrio_code, record: b }));
  }

  // Respects the Alquiler/Compra cross toggle - comparing effort-to-rent vs
  // effort-to-buy is a meaningful choice, not something to hardcode to rent.
  // IMPORTANT: rent and buy are different UNITS (rentEffortPct is a %, buyEffortYears
  // is a count of years), reused here exactly as-is from metrics.js rather than a
  // separate ad-hoc formula - an earlier draft of this function used the rent-only
  // formula (monthly price x12 x60m2) for compra too, which would have divided a
  // one-time purchase price as if it were a recurring monthly rent, producing a
  // meaningless number. The legend note (renderLegend) must say which unit is which.
  // First slider year in which at least 80% of ALL areas at this level (city-wide, not just
  // the drilled-into district, so the baseline doesn't shift between views) have both
  // income and price for `kind`. Usually 2015, but barrio purchase price has zero barrios
  // in 2015 (secrecy threshold) and starts in 2016 - a hardcoded 2015 baseline made
  // compare+Compra blank out every barrio.
  const baselineCache = new Map();
  function compareBaseYear(kind) {
    const key = `${state.level}|${kind}|${state.base}`;
    if (baselineCache.has(key)) return baselineCache.get(key);
    const records = state.level === "district" ? data.districts : [...data.barriosByDistrict.values()].flat();
    // Coverage per year, judged against the BEST year for this kind: some kinds never reach 80% of
    // all areas (barrio "obra nueva" has data for only ~55-69 of 131 barrios in any year), and an
    // absolute 80% would then never find a baseline at all.
    const sortedYears = [...years].sort((a, b) => a - b);
    const counts = sortedYears.map((y) => records.filter((r) => incomeValue(state.level, r, state.base, y) != null && priceValue(state.level, r, kind, y) != null).length);
    const best = Math.max(...counts);
    const found = best > 0 ? sortedYears[counts.findIndex((c) => c >= best * 0.8)] : undefined;
    const base = found ?? Math.min(...years);
    baselineCache.set(key, base);
    return base;
  }
  // Rent source actually used by the MAP: the asking rent of new listings exists only per
  // DISTRICT (no barrio series), so while the map shows barrios it falls back to contracts in
  // force - the user's choice is kept in state.rentSource and comes back at district level.
  // (function declarations, not const arrows: projectionNote()/setYearUI() run during setup,
  // before this point in main() is reached, and a const would still be in its temporal dead zone.)
  function rentSource() { return state.level === "district" && state.rentSource === "oferta" ? "oferta" : "contratos"; }
  function priceKindFor(name) { return activePriceKind(name, state.level, state.rentSource, state.compraType); }
  // Which price the map is using: the layer decides for "alquiler"/"compra", otherwise the cross does.
  function activeFamily() {
    return state.layer === "alquiler" || state.layer === "compra" ? state.layer : state.cross;
  }
  function compareKind() { return priceKindFor(state.cross === "compra" ? "compra" : "alquiler"); }
  const COMPRA_TAGS = { total: "", nueva: " (obra nueva)", usada: " (segunda mano)" };
  const compraTag = () => (COMPRA_TAGS[state.compraType] ?? "");
  const compraLabel = () => ({ total: "precio medio de todas las compraventas", nueva: "obra nueva", usada: "segunda mano" }[state.compraType] ?? "");

  function effortDelta(entry) {
    const level = state.level;
    const baseYear = compareBaseYear(compareKind());
    const effort0 = effortAt(level, entry.record, state.base, compareKind(), baseYear);
    const effort1 = effortAt(level, entry.record, state.base, compareKind(), state.year);
    if (effort0 == null || effort1 == null) return null;
    return effort1 - effort0;
  }

  // Zero-anchored breaks for the compare map: blue ONLY when effort really fell, orange
  // ONLY when it rose, grey only for a negligible change (+-neutral). Quintiles of the
  // data itself (the earlier approach) are relative, so when effort rose almost
  // everywhere the smallest rises were painted blue/grey - wrong sign, wrong story.
  // Strong-change threshold = 66th percentile of |delta|; neutral band floor is 0.25 pp
  // (rent) / 0.25 years (buy) - real district changes 2015-2023 are small (rent effort
  // moves within about +-1.5 pp), so larger floors would paint everything grey.
  function divergingBreaks(deltas) {
    const abs = deltas.filter((d) => d != null && !Number.isNaN(d)).map(Math.abs).sort((a, b) => a - b);
    const floor = 0.25;
    const p66 = abs.length ? abs[Math.min(abs.length - 1, Math.floor(abs.length * 0.66))] : 0;
    const strong = Math.max(p66, floor * 2);
    const neutral = Math.max(strong / 3, floor);
    return [-strong, -neutral, neutral, strong];
  }

  // Every area at the current level (all 21 districts, or all 131 barrios) - the color
  // breaks are computed over THIS, not over the drilled-into district's few barrios, so a
  // barrio's color means the same thing as at city level (and matches the panel's
  // city-wide "Puesto X de N"). Audit finding: breaks used to come from just the visible
  // 3-9 barrios, so e.g. a poor district's barrios were spread across ALL the colors.
  function allEntries() {
    return state.level === "district"
      ? data.districts.map((d) => ({ code: d.district_code, record: d }))
      : data.barrios.map((b) => ({ code: b.barrio_code, record: b }));
  }

  function buildColoring(entries) {
    const level = state.level;
    const scale = allEntries();
    const incomeVals = scale.map((e) => incomeValue(level, e.record, state.base, state.year));
    const incomeBreaks = terciles(incomeVals);

    if (state.compare) {
      const deltas = scale.map(effortDelta);
      const breaks = divergingBreaks(deltas);
      const colorFor = (code) => {
        const e = entries.find((x) => x.code === code);
        const d = e ? effortDelta(e) : null;
        return divergingColor(d, breaks);
      };
      const hasData = (code) => {
        const e = entries.find((x) => x.code === code);
        return e ? effortDelta(e) != null : false;
      };
      return { colorFor, hasData, mode: "diverging", breaks };
    }

    if (state.layer === "cruce") {
      const crossKind = priceKindFor(state.cross);
      const priceVals = scale.map((e) => priceValue(level, e.record, crossKind, state.year));
      const priceBreaks = terciles(priceVals);
      const colorFor = (code) => {
        const e = entries.find((x) => x.code === code);
        return e ? bivariateColor(incomeValue(level, e.record, state.base, state.year), priceValue(level, e.record, crossKind, state.year), incomeBreaks, priceBreaks) : "#E4DED0";
      };
      const hasData = (code) => {
        const e = entries.find((x) => x.code === code);
        return e ? incomeValue(level, e.record, state.base, state.year) != null && priceValue(level, e.record, crossKind, state.year) != null : false;
      };
      return { colorFor, hasData, mode: "grid", incomeBreaks, priceBreaks };
    }

    if (state.layer === "esfuerzo") {
      const breaks = EFFORT_BREAKS[state.base][effortFamily(priceKindFor(state.cross))];
      const effortOf = (code) => {
        const e = entries.find((x) => x.code === code);
        return e ? effortAt(level, e.record, state.base, priceKindFor(state.cross), state.year) : null;
      };
      const colorFor = (code) => {
        const i = classIndex(effortOf(code), breaks);
        return i == null ? "#E4DED0" : EFFORT_RAMP[i];
      };
      const hasData = (code) => effortOf(code) != null;
      return { colorFor, hasData, mode: "strip-effort", breaks };
    }

    if (state.layer === "renta") {
      const colorFor = (code) => {
        const e = entries.find((x) => x.code === code);
        return e ? colorForValue(incomeValue(level, e.record, state.base, state.year), incomeBreaks, INCOME_RAMP) : "#E4DED0";
      };
      const hasData = (code) => {
        const e = entries.find((x) => x.code === code);
        return e ? incomeValue(level, e.record, state.base, state.year) != null : false;
      };
      return { colorFor, hasData, mode: "strip-income", breaks: incomeBreaks };
    }

    // alquiler or compra
    const kind = priceKindFor(state.layer);
    const priceVals = scale.map((e) => priceValue(level, e.record, kind, state.year));
    const priceBreaks = terciles(priceVals);
    const colorFor = (code) => {
      const e = entries.find((x) => x.code === code);
      return e ? colorForValue(priceValue(level, e.record, kind, state.year), priceBreaks, PRICE_RAMP) : "#E4DED0";
    };
    const hasData = (code) => {
      const e = entries.find((x) => x.code === code);
      return e ? priceValue(level, e.record, kind, state.year) != null : false;
    };
    return { colorFor, hasData, mode: "strip-price", breaks: priceBreaks };
  }

  function renderLegend(coloring) {
    if (coloring.mode === "grid") {
      legendGridWrap.hidden = false;
      legendStripWrap.hidden = true;
      legendAxisLabel.textContent = `${state.cross === "alquiler" ? (rentSource() === "oferta" ? "Alquiler (oferta)" : "Alquiler") : "Compra" + compraTag()} por m² →`;
      const cells = [];
      [2, 1, 0].forEach((p) => [0, 1, 2].forEach((i) => cells.push(BIVARIATE_GRID[`${i}${p}`])));
      legendGrid.innerHTML = cells.map((c) => `<div style="background:${c}"></div>`).join("");
      legendNote.innerHTML = `<span style="font-weight:700;color:#B4560F">Naranja</span>: precio alto para la renta. <span style="font-weight:700;color:#2F5D8C">Azul</span>: renta holgada frente al precio.` + projectionSuffix("grid");
      return;
    }
    legendGridWrap.hidden = true;
    legendStripWrap.hidden = false;
    let colors = PRICE_RAMP, left = "Precio bajo", right = "Precio alto", note = "";
    if (coloring.mode === "diverging") {
      colors = DIVERGING; left = "Bajó el esfuerzo"; right = "Subió el esfuerzo";
      const strong = coloring.breaks[3], neutral = coloring.breaks[2];
      const f = (v) => v.toLocaleString("es-ES", { maximumFractionDigits: 1 });
      const unit = state.cross === "compra" ? "años" : "pp";
      note = (state.cross === "compra"
        ? `Cambio del esfuerzo de compra (80 m², ${compraLabel()}) entre ${compareBaseYear(compareKind())} y ${state.year}, en años de renta.`
        : `Cambio del esfuerzo de alquiler (60 m², ${rentSource() === "oferta" ? "precio de oferta" : "contratos en vigor"}) entre ${compareBaseYear(compareKind())} y ${state.year}, en puntos porcentuales.`)
        + ` Gris: cambio menor de ±${f(neutral)} ${unit}. Colores intensos: más de ±${f(strong)} ${unit}. Azul solo si el esfuerzo bajó de verdad, naranja si subió.`;
    } else if (coloring.mode === "strip-effort") {
      const b = coloring.breaks;
      colors = EFFORT_RAMP; left = "Menos esfuerzo"; right = "Más esfuerzo";
      const who = state.base === "persona" ? "por persona" : "del hogar";
      note = state.cross === "compra"
        ? `Años de renta neta ${who} para comprar ${EFFORT_M2.compra} m² (${compraLabel()}): menos de ${b[0]}, ${b[0]}–${b[1]}, ${b[1]}–${b[2]}, ${b[2]}–${b[3]}, más de ${b[3]} años.`
        : `% de la renta neta anual ${who} para alquilar ${EFFORT_M2.alquiler} m² (${rentSource() === "oferta" ? "precio de oferta: anuncios de nuevos contratos" : "alquiler de contratos en vigor"}): menos del ${b[0]} %, ${b[0]}–${b[1]}, ${b[1]}–${b[2]}, ${b[2]}–${b[3]}, más del ${b[3]} %.`
          + (state.base === "hogar" ? " El 30 % suele usarse como referencia de carga elevada." : "");
      note += state.base === "persona"
        ? " Con la renta por persona los umbrales son más altos (un hogar medio tiene unas 2,6 personas), así que no se comparan con los del hogar. Umbrales fijos: el mismo color significa lo mismo en cualquier año."
        : " Umbrales fijos: el mismo color significa lo mismo en cualquier año.";
    } else if (coloring.mode === "strip-income") {
      colors = INCOME_RAMP; left = "Renta baja"; right = "Renta alta";
      note = state.base === "hogar" ? "Renta neta media por hogar." : "Renta neta media por persona.";
    } else {
      note = state.layer === "alquiler" ? (rentSource() === "oferta" ? "Alquiler, precio de oferta (anuncios de nuevos contratos), €/m² al mes." : "Alquiler de contratos en vigor, €/m² al mes.") : `Compra (${compraLabel()}), €/m².`;
    }
    legendStrip.innerHTML = colors.map((c) => `<div style="background:${c}"></div>`).join("");
    stripLeftEl.textContent = left;
    stripRightEl.textContent = right;
    legendNote.textContent = note + projectionSuffix(coloring.mode);
  }

  // Which of the metrics this map mode actually colors by are projected this year.
  function projectionSuffix(mode) {
    const y = state.year;
    const usesIncome = mode !== "strip-price";
    const usesRent = rentSource() === "contratos" && ((mode === "strip-price" && state.layer === "alquiler") || ((mode === "grid" || mode === "diverging" || mode === "strip-effort") && state.cross === "alquiler"));
    const parts = [];
    if (usesIncome && y > lastIncomeYear) parts.push("la renta");
    if (usesRent && y > lastRentYear) parts.push("el alquiler");
    if (!parts.length) return "";
    return ` * Proyección para ${y}: ${parts.join(" y ")} no están publicados aún y se estiman con su tendencia reciente.`;
  }

  // Shows whatever value the map is ACTUALLY colored by, not always income - the four
  // branches here mirror buildColoring()'s four modes exactly (diverging/grid/strip-income/
  // strip-price), so hovering always explains the color under the cursor.
  function tooltipText(codeProp, entries) {
    return (code) => {
      const e = entries.find((x) => x.code === code);
      const name = codeProp === "district_code" ? e?.record.district_name : e?.record.barrio_name;
      if (!e) return `${name ?? ""} — sin datos`;
      const level = state.level;

      // "*" marks a value that is a projection for this year (see metrics.js isProjected).
      const star = (kind) => (isProjected(kind, level, e.record, state.base, state.year) ? "*" : "");
      const rentStar = state.cross === "compra" || rentSource() === "oferta" ? "" : star("alquiler");
      const rentTag = rentSource() === "oferta" ? " (oferta)" : "";
      const buyTag = compraTag();

      if (state.compare) {
        const d = effortDelta(e);
        if (d == null) return `${name} — sin datos`;
        const unit = state.cross === "compra" ? "años" : "puntos";
        const anyProj = star("renta") || rentStar;
        return `${name} — ${deltaPct.format(d)} ${unit}${anyProj ? "*" : ""}`;
      }

      if (state.layer === "esfuerzo") {
        const v = effortAt(level, e.record, state.base, priceKindFor(state.cross), state.year);
        if (v == null) return `${name} — sin datos`;
        const anyProj = star("renta") || rentStar;
        return state.cross === "compra"
          ? `${name} — ${v.toFixed(1)} años de renta para comprar ${EFFORT_M2.compra} m²${buyTag}${anyProj ? "*" : ""}`
          : `${name} — ${v.toFixed(0)} % de la renta para alquilar ${EFFORT_M2.alquiler} m²${rentTag}${anyProj ? "*" : ""}`;
      }

      if (state.layer === "cruce") {
        const income = incomeValue(level, e.record, state.base, state.year);
        const price = priceValue(level, e.record, priceKindFor(state.cross), state.year);
        const incomeTxt = income != null ? euro.format(income) + star("renta") : "sin datos";
        const priceTxt = price != null ? `${euroM2.format(price)} €/m²${rentStar}` : "sin datos";
        const priceLabel = state.cross === "compra" ? `Compra${buyTag}` : `Alquiler${rentTag}`;
        return `${name} — Renta ${incomeTxt} · ${priceLabel} ${priceTxt}`;
      }

      if (state.layer === "renta") {
        const value = incomeValue(level, e.record, state.base, state.year);
        return `${name} — ${value != null ? euro.format(value) + star("renta") : "sin datos"}`;
      }

      // alquiler or compra layer
      const value = priceValue(level, e.record, priceKindFor(state.layer), state.year);
      return `${name} — ${value != null ? `${euroM2.format(value)} €/m²${state.layer === "alquiler" ? rentStar + rentTag : buyTag}` : "sin datos"}`;
    };
  }

  function updateBreadcrumb() {
    if (state.level === "district") {
      crumbMadrid.disabled = true;
      crumbDistrictWrap.hidden = true;
      mapHint.textContent = "Haz clic en un distrito, o busca tu código postal";
    } else {
      crumbMadrid.disabled = false;
      crumbDistrictWrap.hidden = false;
      crumbDistrict.textContent = data.districtsByCode.get(state.districtCode)?.district_name ?? "";
      crumbDistrict.disabled = true;
      mapHint.textContent = "Haz clic en un barrio para ver su detalle";
    }
  }

  // Patches just an effort card's own two numbers from its slider's "input" event,
  // WITHOUT calling the full render() - calling render() on every tick of a drag
  // rebuilds the whole panel via innerHTML, which destroys and recreates the slider
  // element itself mid-drag and makes dragging barely work. Nothing else in the
  // panel/map depends on rentM2/buyM2, so this direct DOM patch is fully correct,
  // not just a performance shortcut - a full render is never actually needed here.
  function liveUpdateEffortCard(slider, stateKey) {
    const m2 = Number(slider.value);
    state[stateKey] = m2;
    const card = slider.closest(".effort-card");
    const price = slider.dataset.price === "" ? null : Number(slider.dataset.price);
    const income = slider.dataset.income === "" ? null : Number(slider.dataset.income);
    const value = slider.dataset.mode === "rent" ? rentEffortPct(price, m2, income) : buyEffortYears(price, m2, income);
    const unit = slider.dataset.mode === "rent" ? "%" : "años";
    card.querySelector(".big").textContent = value != null ? `${value.toFixed(0)} ${unit}${slider.dataset.proj ? "*" : ""}` : "Sin datos";
    card.querySelector(".m2-value").textContent = `${m2} m²`;
    const extraEl = card.querySelector(".effort-extra-value");
    if (extraEl && slider.dataset.priceAsk !== "") {
      const askValue = rentEffortPct(Number(slider.dataset.priceAsk), m2, income);
      extraEl.textContent = askValue != null ? `${askValue.toFixed(0)} %${slider.dataset.proj ? "*" : ""}` : "Sin datos";
    }
  }

  function wirePanelInteractions() {
    const goBarrios = document.getElementById("go-barrios-btn");
    if (goBarrios) goBarrios.addEventListener("click", () => { state.level = "barrio"; state.selectedBarrioCode = null; render(); });
    const rentSlider = document.getElementById("rent-m2-slider");
    if (rentSlider) rentSlider.addEventListener("input", () => liveUpdateEffortCard(rentSlider, "rentM2"));
    const buySlider = document.getElementById("buy-m2-slider");
    if (buySlider) buySlider.addEventListener("input", () => liveUpdateEffortCard(buySlider, "buyM2"));
  }

  function runSearch(query) {
    const q = query.trim();
    const candidates = data.postalCodes[q];
    if (!candidates) {
      searchResults.hidden = true;
      searchResults.innerHTML = "";
      return;
    }
    searchResults.hidden = false;
    searchResults.innerHTML = candidates.map((c) => `<button type="button" data-code="${c.barrio_code}">${c.barrio_name} <span class="share">(${Math.round(c.share * 100)}% de ${q})</span></button>`).join("");
    searchResults.querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", () => {
        const code = btn.dataset.code;
        state.level = "barrio";
        state.districtCode = code.slice(0, 2);
        state.selectedBarrioCode = code;
        searchResults.hidden = true;
        searchInput.value = "";
        render();
      });
    });
  }

  searchBtn.addEventListener("click", () => runSearch(searchInput.value));
  searchInput.addEventListener("keydown", (e) => { if (e.key === "Enter") runSearch(searchInput.value); });

  function render() {
    const entries = currentEntries();
    const coloring = buildColoring(entries);
    const codeProp = state.level === "district" ? "district_code" : "barrio_code";
    const featureCollection = state.level === "district"
      ? data.distritosGeo
      : { type: "FeatureCollection", features: data.barriosGeo.features.filter((f) => f.properties.barrio_code.slice(0, 2) === state.districtCode) };

    renderMap(svg, featureCollection, {
      codeProp,
      colorFor: coloring.colorFor,
      hasData: coloring.hasData,
      selectedCode: state.level === "barrio" ? state.selectedBarrioCode : null,
      onClick: (code) => {
        if (state.level === "district") {
          state.level = "barrio";
          state.districtCode = code;
          state.selectedBarrioCode = null;
        } else {
          state.selectedBarrioCode = code;
        }
        render();
      },
      tooltipText: tooltipText(codeProp, entries),
      showLabels: state.level === "barrio",
    });

    renderPanel(panelContainer, state, data);
    wirePanelInteractions();
    renderLegend(coloring);
    updateBreadcrumb();
    // Whole map grey (e.g. Compra in 2015, when the registry publishes no barrio prices) would
    // look like a bug - say why instead.
    if (!entries.some((e) => coloring.hasData(e.code))) {
      mapHint.textContent = "Sin datos para esta combinación de año y capa (p. ej. el registro no publica precios por barrio en 2015).";
    }

    buttonGroup(layerButtons, LAYERS, state.layer, pickLayer, new Set()); // compra layer works at both levels
    crossSection.hidden = state.layer !== "cruce" && state.layer !== "esfuerzo";
    // One switch for the price the map is using: rent (contratos / oferta) or purchase (total /
    // nueva / usada). Hidden only on the Renta layer, which uses no price.
    const family = activeFamily();
    priceSourceSection.hidden = state.layer === "renta";
    priceSourceLabel.textContent = family === "compra" ? "Compra según" : "Alquiler según";
    if (family === "compra") {
      buttonGroup(priceSourceButtons, COMPRA_TYPES, state.compraType, pickPriceSource);
      priceSourceNote.textContent = state.compraType === "total"
        ? "Precio medio de todas las compraventas (obra nueva y segunda mano, ponderado por las ventas reales)."
        : state.level === "barrio"
          ? "Con pocas ventas por barrio el registro no publica el dato: verás muchos barrios en gris" + (state.compraType === "nueva" ? " (la obra nueva es la más escasa)." : ".")
          : state.compraType === "nueva" ? "Solo viviendas nuevas: una serie más irregular." : "Solo viviendas de segunda mano.";
    } else {
      buttonGroup(priceSourceButtons, RENT_SOURCES, rentSource(), pickPriceSource, state.level === "barrio" ? new Set(["oferta"]) : new Set());
      priceSourceNote.textContent = state.level === "barrio"
        ? "El precio de oferta solo existe por distrito: en los barrios se muestran los contratos en vigor."
        : rentSource() === "oferta"
          ? "Anuncios de nuevos contratos (Idealista, vía Ayto. de Madrid), 2011-2024, sin proyección: es lo que pide hoy un propietario."
          : "Alquiler de los contratos ya firmados que declaran los propietarios a Hacienda (SERPAVI): queda por debajo de los anuncios actuales.";
    }
    setYearUI();
    buttonGroup(crossButtons, CROSSES, state.cross, pickCross, new Set()); // compra cross works at both levels too, now that barrio purchase is a real series
    buttonGroup(baseButtons, BASES, state.base, pickBase);
    baseNote.textContent = state.base === "hogar" ? "El esfuerzo se calcula con la renta neta media del hogar." : "El esfuerzo se calcula con la renta neta media por persona.";
    compareBtn.classList.toggle("active", state.compare);
    compareBtn.textContent = `Comparar con ${compareBaseYear(compareKind())}`;
  }

  render();
  window.addEventListener("resize", render);
}

main().catch((err) => {
  console.error(err);
  panelContainer.innerHTML = `<p class="placeholder-text">Error cargando los datos: ${err.message}</p>`;
});
