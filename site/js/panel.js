import { incomeValue, priceValue, isProjected, effortAt, activePriceKind, cityAverage, pctDelta, rentEffortPct, buyEffortYears, indexSeries, extrapolateForward, rankOf } from "./metrics.js";

const CURRENT_YEAR = 2026;

const euro = new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
const euroM2 = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 2 });
const pct = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 0, signDisplay: "always" });

// `reference` is the simple (unweighted) mean of the areas at this level, NOT a
// household-weighted Madrid-wide figure, so the label says exactly that.
function deltaLabel(value, reference, level) {
  const d = pctDelta(value, reference);
  return d == null ? "" : `${pct.format(d)}% vs. media de ${level === "district" ? "distritos" : "barrios"}`;
}

function valueRow(name, src, amount, kind, delta) {
  return `
    <div class="value-row">
      <div class="value-row-label"><span class="name">${name}</span><span class="src">${src}</span></div>
      <div class="value-row-amount">
        <span class="amount ${kind}">${amount ?? "Sin datos"}</span>
        <span class="delta">${delta}</span>
      </div>
    </div>`;
}

// mode/price/income are baked in as data-* attributes so main.js can recompute
// and patch just this card's numbers on every slider "input" tick WITHOUT doing a
// full panel re-render (which would destroy and recreate the slider mid-drag - see
// wirePanelInteractions in main.js for why that broke dragging).
function effortCard({ title, big, sub, m2Label, m2, min, max, sliderId, mode, price, income, proj, extra }) {
  return `
    <div class="effort-card">
      <span class="label">${title}</span>
      <span class="big">${big}</span>
      <span class="sub">${sub}</span>
      ${extra ? `<span class="sub effort-extra">${extra.label} <strong class="effort-extra-value">${extra.text}</strong></span>` : ""}
      <div class="m2-row"><span>Superficie</span><span class="m2-value">${m2} m²</span></div>
      <input type="range" id="${sliderId}" min="${min}" max="${max}" step="5" value="${m2}" aria-label="${m2Label}"
        data-mode="${mode}" data-price="${price ?? ""}" data-income="${income ?? ""}" data-proj="${proj ? "1" : ""}" data-price-ask="${extra?.price ?? ""}">
    </div>`;
}

// One line per price kind (1 for alquiler, 2 for compra - nueva/usada are
// methodologically different, see metrics.js, and must never be shown as one
// blended line here), plus the income line. Each line is an INDEPENDENT series
// (its own years/idx, see metrics.js's realSeries) - a metric with more recent real
// data (e.g. rent through 2024) shows all of it, even where another metric (income,
// 2023) has already run out; each line's dashed projection starts from ITS OWN last
// real point, not a shared cutoff. priceMeta: [{kind, label, color, dash}], same
// order as series.priceSeries.
function indexChartSvg(series, rankLabel, currentYear, priceMeta) {
  if (!series) {
    return `<p class="rail-note">Sin serie suficiente para el índice.</p>`;
  }
  const { income, priceSeries, missingKinds } = series;
  const x0 = 30, x1 = 330, yTop = 10, yBottom = 140;
  const metaFor = (kind) => priceMeta.find((m) => m.kind === kind);

  const lineDefs = [
    { key: "renta", label: "Renta", unit: "€/año", fmt: (v) => euro.format(v), color: "#2F5D8C", dash: null, years: income.years, idx: income.idx, vals: income.vals },
    ...priceSeries.map((p) => {
      const m = metaFor(p.kind);
      return { key: p.kind, label: m.label, unit: m.unit, fmt: (v) => euroM2.format(v), color: m.color, dash: m.dash, years: p.years, idx: p.idx, vals: p.vals };
    }),
  ].map((d) => ({ ...d, ...extrapolateForward(d.years, d.idx, CURRENT_YEAR) }));
  const hasProjection = lineDefs.some((d) => d.extYears.length > 1);

  const domainStart = Math.min(...lineDefs.map((d) => d.years[0]));
  const domainEnd = Math.max(CURRENT_YEAR, ...lineDefs.map((d) => d.years[d.years.length - 1]));
  const scaleX = (year) => x0 + ((year - domainStart) / (domainEnd - domainStart)) * (x1 - x0);

  const allVals = lineDefs.flatMap((d) => d.idx.concat(d.extIdx));
  const min = Math.min(100, ...allVals), max = Math.max(100, ...allVals);
  const pad = (max - min) * 0.15 || 10;
  const scaleY = (v) => yBottom - ((v - (min - pad)) / ((max + pad) - (min - pad))) * (yBottom - yTop);
  const pointsFor = (ys, vals) => ys.map((y, i) => `${scaleX(y)},${scaleY(vals[i])}`).join(" ");
  const baselineY = scaleY(100);

  // Highlight the slider's current year on EACH line independently (a line's own
  // years array might not be identical to another's) - falls back to the closest
  // real year that particular line actually has.
  function markerFor(d) {
    const extAt = d.extYears.indexOf(currentYear);
    if (currentYear > d.years[d.years.length - 1] && extAt > 0) {
      return { x: scaleX(currentYear), y: scaleY(d.extIdx[extAt]) };
    }
    const idx = d.years.includes(currentYear)
      ? d.years.indexOf(currentYear)
      : d.years.reduce((best, y, i) => (Math.abs(y - currentYear) < Math.abs(d.years[best] - currentYear) ? i : best), 0);
    return { x: scaleX(d.years[idx]), y: scaleY(d.idx[idx]) };
  }

  // Label each line at its OWN actual endpoint (real end, or projected end when
  // there is one - never a fixed position, real data can put any line on top),
  // stacked top-to-bottom with a minimum gap so lines ending close together don't
  // overlap each other.
  const endValue = (d) => (d.extIdx.length ? d.extIdx[d.extIdx.length - 1] : d.idx[d.idx.length - 1]);
  const endpoints = lineDefs.map((d) => ({ key: d.key, endY: scaleY(endValue(d)) })).sort((a, b) => a.endY - b.endY);
  const labelY = {};
  let prevY = -Infinity;
  for (const e of endpoints) {
    let y = e.endY - 8;
    if (y - prevY < 14) y = prevY + 14;
    labelY[e.key] = y;
    prevY = y;
  }

  // Hover points: pure CSS (`.pt:hover .pt-tip` in style.css), no JS and no re-render, so
  // hovering can't destroy anything mid-interaction. Each real year gets a transparent
  // larger hit circle + small visible dot; the tooltip shows the actual underlying value
  // (€ or €/m²) AND the index, so the chart isn't only readable relative to 100.
  const ptsSvg = (d) => d.years.map((yr, i) => {
    const cx = scaleX(yr), cy = scaleY(d.idx[i]);
    const text = `${yr} · ${d.label}: ${d.fmt(d.vals[i])} ${d.unit} · índice ${Math.round(d.idx[i])}`;
    const w = Math.min(Math.round(text.length * 5.4 + 12), 332);
    const tx = Math.min(Math.max(cx - w / 2, 2), 334 - w);
    const ty = cy - 30 < 0 ? cy + 10 : cy - 30;
    return `<g class="pt"><circle cx="${cx}" cy="${cy}" r="9" fill="transparent"></circle><circle class="pt-dot" cx="${cx}" cy="${cy}" r="2.5" fill="${d.color}"></circle>
      <g class="pt-tip"><rect x="${tx}" y="${ty}" width="${w}" height="20" rx="4" fill="#1C1B18"></rect><text x="${tx + 6}" y="${ty + 14}" font-size="10.5" fill="#FAF7F0">${text}</text></g></g>`;
  }).join("");
  const extPtsSvg = (d) => d.extYears.slice(1).map((yr, j) => {
    const i = j + 1;
    const cx = scaleX(yr), cy = scaleY(d.extIdx[i]);
    const text = `${yr} · ${d.label}: proyección (índice ${Math.round(d.extIdx[i])})`;
    const w = Math.round(text.length * 5.6 + 12);
    const tx = Math.min(Math.max(cx - w / 2, 2), 334 - w);
    const ty = cy - 30 < 0 ? cy + 10 : cy - 30;
    return `<g class="pt"><circle cx="${cx}" cy="${cy}" r="9" fill="transparent"></circle>
      <g class="pt-tip"><rect x="${tx}" y="${ty}" width="${w}" height="20" rx="4" fill="#1C1B18"></rect><text x="${tx + 6}" y="${ty + 14}" font-size="10.5" font-style="italic" fill="#FAF7F0">${text}</text></g></g>`;
  }).join("");

  const linesSvg = lineDefs.map((d) => {
    const marker = markerFor(d);
    return `
      <polyline points="${pointsFor(d.years, d.idx)}" fill="none" stroke="${d.color}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"${d.dash ? ` stroke-dasharray="${d.dash}"` : ""}></polyline>
      ${d.extYears.length > 1 ? `<polyline points="${pointsFor(d.extYears, d.extIdx)}" fill="none" stroke="${d.color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" stroke-dasharray="2 3" opacity="0.55"></polyline>` : ""}
      <circle cx="${marker.x}" cy="${marker.y}" r="5" fill="${d.color}" stroke="#FAF7F0" stroke-width="2"></circle>
      <text x="${x1}" y="${labelY[d.key]}" text-anchor="end" font-size="12" font-weight="700" fill="${d.color}">${d.label}</text>`;
  }).join("");

  const lastRealYear = Math.max(...lineDefs.map((d) => d.years[d.years.length - 1]));
  const endYearLabel = hasProjection ? `${domainEnd} (proy.)` : `${lastRealYear}`;

  return `
    <svg viewBox="0 0 336 168" role="img" aria-label="Evolución del índice de renta y precio desde ${domainStart}${hasProjection ? `, con proyección hasta ${domainEnd}` : ""}">
      <line x1="${x0}" y1="${baselineY}" x2="${x1}" y2="${baselineY}" stroke="#8F8878" stroke-width="1" stroke-dasharray="3 3"></line>
      <text x="0" y="${baselineY + 4}" font-size="12" fill="#5E5A50">100</text>
      ${linesSvg}
      ${lineDefs.map((d) => ptsSvg(d) + extPtsSvg(d)).join("")}
      <text x="${x0}" y="160" font-size="12" fill="#5E5A50">${domainStart}</text>
      <text x="${x1}" y="160" text-anchor="end" font-size="12" font-style="${hasProjection ? "italic" : "normal"}" fill="#5E5A50">${endYearLabel}</text>
    </svg>
    <div style="display:flex;justify-content:space-between;align-items:baseline">
      ${hasProjection ? `<span class="projection-note">┄ proyección, no es un dato real</span>` : "<span></span>"}
      <span class="rank-label">${rankLabel}</span>
    </div>
    ${missingKinds.length ? `<p class="rail-note">Sin serie suficiente para: ${missingKinds.map((k) => metaFor(k).label).join(", ")} (pocas compraventas para publicar el dato en este barrio).</p>` : ""}`;
}

const PRICE_META = {
  alquiler: [
    { kind: "alquiler", label: "Alquiler", unit: "€/m²/mes", color: "#B4560F", dash: null },
    { kind: "alquiler_oferta", label: "Oferta", unit: "€/m²/mes", color: "#E5A56B", dash: null },
  ],
  compra: [
    { kind: "compra_nueva", label: "Compra (nueva)", unit: "€/m²", color: "#B4560F", dash: null },
    { kind: "compra_usada", label: "Compra (usada)", unit: "€/m²", color: "#E5A56B", dash: null },
  ],
};

function renderArea({ level, record, entries, state, extraNote, ctaHtml }) {
  const { year, base, cross, rentM2, buyM2 } = state;
  const income = incomeValue(level, record, base, year);
  const rent = priceValue(level, record, "alquiler", year);
  const rentAsk = priceValue(level, record, "alquiler_oferta", year); // district only, asking rent of new listings
  const compra = priceValue(level, record, "compra", year); // total price, for the effort card + rank
  const compraNueva = priceValue(level, record, "compra_nueva", year);
  const compraUsada = priceValue(level, record, "compra_usada", year);

  const cityIncome = cityAverage(entries, (e) => incomeValue(level, e.record, base, year));
  const cityRent = cityAverage(entries, (e) => priceValue(level, e.record, "alquiler", year));
  const cityRentAsk = cityAverage(entries, (e) => priceValue(level, e.record, "alquiler_oferta", year));
  const cityCompraNueva = cityAverage(entries, (e) => priceValue(level, e.record, "compra_nueva", year));
  const cityCompraUsada = cityAverage(entries, (e) => priceValue(level, e.record, "compra_usada", year));

  const rentPct = rentEffortPct(rent, rentM2, income);
  const buyYears = buyEffortYears(compra, buyM2, income);

  // Union of every year ANY relevant metric has, not just income's - income stops
  // sooner than rent at both levels (and purchase covers a wider/different range
  // again, 2015-2025 at barrio level), and if the candidate list only came from
  // income's own keys, the other metrics' own real years would never even be checked.
  const years = level === "district"
    ? Object.keys(record?.timeseries ?? {}).map(Number).sort((a, b) => a - b)
    : [...new Set([
        ...Object.keys(record?.income ?? {}),
        ...Object.keys(record?.rent ?? {}),
        ...Object.keys(record?.purchase ?? {}),
      ])].map(Number).sort((a, b) => a - b);
  const priceKinds = cross === "compra" ? ["compra_nueva", "compra_usada"] : level === "district" ? ["alquiler", "alquiler_oferta"] : ["alquiler"];
  const series = indexSeries(level, record, base, priceKinds, years);

  // Same price-kind rule as the map (main.js priceKindFor), so the rank matches the colours.
  const kindOf = (name) => activePriceKind(name, state.level, state.rentSource, state.compraType);
  const metricFor = {
    renta: (r) => incomeValue(level, r, base, year),
    alquiler: (r) => priceValue(level, r, kindOf("alquiler"), year),
    compra: (r) => priceValue(level, r, kindOf("compra"), year),
    esfuerzo: (r) => effortAt(level, r, base, kindOf(cross), year),
  };
  const rankMetric = metricFor[state.layer] || metricFor.renta;
  const rank = rankOf(record.code, entries, (e) => rankMetric(e.record));
  const rankLabel = rank ? `Puesto ${rank.rank} de ${rank.total}` : "";

  const incomeLabel = base === "persona" ? "Renta neta por persona" : "Renta neta por hogar";
  const incomeSrc = level === "barrio" ? "€/año · INE, de secciones" : "€/año · INE";
  const rentSrc = level === "barrio" ? "€/m²/mes · MIVAU, de secciones" : "€/m²/mes · MIVAU";
  // nueva/usada/total are all Colegio de Registradores (real registered transactions), official at
  // BOTH levels (district figures come straight from the Ayuntamiento's Banco de Datos).
  const compraNuevaSrc = "€/m² · Colegio de Registradores";
  const compraUsadaSrc = "€/m² · Colegio de Registradores";

  // "*" = projection for this year (income real to 2023, rent to 2024; see metrics.js).
  const incomeProj = income != null && isProjected("renta", level, record, base, year);
  const rentProj = rent != null && isProjected("alquiler", level, record, base, year);
  const incomeSrcP = incomeProj ? incomeSrc + " · proyección*" : incomeSrc;
  const rentSrcP = rentProj ? rentSrc + " · proyección*" : rentSrc;
  const projNote = (incomeProj || rentProj)
    ? `<p class="rail-note">* ${[incomeProj ? "renta" : null, rentProj ? "alquiler" : null].filter(Boolean).join(" y ")} de ${year} proyectad${incomeProj && rentProj ? "os" : incomeProj ? "a" : "o"} con la tendencia de los últimos años: no es un dato publicado. Los esfuerzos calculados con ese valor también son una estimación.</p>`
    : "";

  const rows = valueRow(incomeLabel, incomeSrcP, income != null ? euro.format(income) + (incomeProj ? "*" : "") : null, "income", deltaLabel(income, cityIncome, level))
    + valueRow("Alquiler (contratos en vigor)", rentSrcP, rent != null ? `${euroM2.format(rent)} €${rentProj ? "*" : ""}` : null, "price", deltaLabel(rent, cityRent, level))
    + (level === "district"
      ? valueRow("Alquiler (precio de oferta)", "€/m²/mes · anuncios de nuevos contratos (Idealista, vía Ayto. de Madrid)", rentAsk != null ? `${euroM2.format(rentAsk)} €` : null, "price", deltaLabel(rentAsk, cityRentAsk, level))
      : valueRow("Alquiler (precio de oferta)", "solo disponible por distrito", "—", "price", ""))
    + valueRow("Compra (obra nueva)", compraNuevaSrc, compraNueva != null ? `${euroM2.format(compraNueva)} €` : null, "price", deltaLabel(compraNueva, cityCompraNueva, level))
    + valueRow("Compra (segunda mano)", compraUsadaSrc, compraUsada != null ? `${euroM2.format(compraUsada)} €` : null, "price", deltaLabel(compraUsada, cityCompraUsada, level));

  const rentSub = base === "persona" ? "de tu renta neta anual" : "de la renta neta anual del hogar";
  // This card uses the TOTAL price (all sales), unlike the value rows and the chart
  // above, which split nueva/usada - said explicitly so it isn't silently inconsistent.
  const buySub = (base === "persona" ? "de renta neta íntegra personal" : "de renta neta íntegra del hogar") + " · precio medio de todas las compraventas";

  // District only: what the same 60 m2 costs at today's ASKING rent (new contracts), next to the
  // contracts-in-force figure that is the card's main number.
  const askPct = rentAsk != null ? rentEffortPct(rentAsk, rentM2, income) : null;
  const askExtra = level === "district" && rentAsk != null
    ? { label: "Con el precio de oferta actual:", text: askPct != null ? `${askPct.toFixed(0)} %${incomeProj ? "*" : ""}` : "Sin datos", price: rentAsk }
    : null;

  const cards = `<div class="effort-cards">`
    + effortCard({ title: "Alquilar", big: rentPct != null ? `${rentPct.toFixed(0)} %${incomeProj || rentProj ? "*" : ""}` : "Sin datos", sub: rentSub, m2Label: "Metros cuadrados a alquilar", m2: rentM2, min: 30, max: 120, sliderId: "rent-m2-slider", mode: "rent", price: rent, income, proj: incomeProj || rentProj, extra: askExtra })
    + effortCard({ title: "Comprar", big: buyYears != null ? `${buyYears.toFixed(0)} años${incomeProj ? "*" : ""}` : "Sin datos", sub: buySub, m2Label: "Metros cuadrados a comprar", m2: buyM2, min: 40, max: 150, sliderId: "buy-m2-slider", mode: "buy", price: compra, income, proj: incomeProj })
    + `</div>`;

  const chart = `
    <div class="index-chart">
      <div class="index-chart-head"><span class="index-label">Renta y precio · índice (100 = primer año con dato de cada serie)</span></div>
      ${indexChartSvg(series, rankLabel, year, PRICE_META[cross])}
    </div>`;

  return `
    <p class="panel-kicker">${level === "district" ? "Distrito seleccionado" : "Barrio"} · ${year}</p>
    <h2 class="panel-title">${record.name}</h2>
    ${extraNote ?? ""}
    ${ctaHtml ?? ""}
    <div class="value-rows">${rows}</div>
    ${cards}
    ${projNote}
    ${chart}
    <div class="sources" id="fuentes">Fuentes: INE, Atlas de Distribución de Renta de los Hogares · MIVAU, SERPAVI · Ayuntamiento de Madrid, estadística registral inmobiliaria. Renta y precio se comparan del mismo año. <a href="metodologia.html">Metodología completa →</a></div>`;
}

export function renderPanel(container, state, data) {
  if (state.level === "district" && !state.districtCode) {
    container.innerHTML = `<p class="placeholder-text">Haz clic en un distrito para empezar.</p>`;
    return;
  }

  if (state.level === "district") {
    const record = data.districtsByCode.get(state.districtCode);
    const entries = data.districts.map((d) => ({ code: d.district_code, record: d }));
    const barrioCount = (data.barriosByDistrict.get(state.districtCode) || []).length;
    container.innerHTML = renderArea({
      level: "district",
      record: { code: record.district_code, name: record.district_name, timeseries: record.timeseries },
      entries,
      state,
      ctaHtml: `<button type="button" class="btn-outline" id="go-barrios-btn">Ver los ${barrioCount} barrios →</button>`,
    });
    return;
  }

  // level === 'barrio'
  const district = data.districtsByCode.get(state.districtCode);
  if (!state.selectedBarrioCode) {
    const entries = data.districts.map((d) => ({ code: d.district_code, record: d }));
    container.innerHTML = renderArea({
      level: "district",
      record: { code: district.district_code, name: district.district_name, timeseries: district.timeseries },
      entries,
      state,
      extraNote: `<p class="panel-note">Datos del distrito completo. Haz clic en un barrio para ver su detalle.</p>`,
    });
    return;
  }

  const barrio = data.barriosByCode.get(state.selectedBarrioCode);
  const entries = data.barrios.map((b) => ({ code: b.barrio_code, record: b }));
  container.innerHTML = renderArea({
    level: "barrio",
    record: { code: barrio.barrio_code, name: barrio.barrio_name, income: barrio.income, rent: barrio.rent, purchase: barrio.purchase },
    entries,
    state,
    extraNote: `<p class="panel-note">Renta y alquiler se calculan sumando las secciones censales del barrio, ponderadas por hogares.</p>`,
  });
}
