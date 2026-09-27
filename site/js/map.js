import { NO_DATA_COLOR, textColorFor } from "./colors.js";

const tooltip = document.getElementById("tooltip");

function showTooltip(event, text) {
  tooltip.textContent = text;
  tooltip.hidden = false;
  tooltip.style.left = `${event.offsetX}px`;
  tooltip.style.top = `${event.offsetY}px`;
}

function hideTooltip() {
  tooltip.hidden = true;
}

// How wide the polygon actually is at the label's own height, not the shape's
// overall bounding box - a shape can be wide at the top and bottom but pinched
// narrow exactly where its centroid (and therefore the label) sits, so the
// bounding box alone understates how much a label there can overflow.
function ringCrossingsAtY(projectedRing, y) {
  const xs = [];
  for (let i = 0; i < projectedRing.length; i++) {
    const [x1, y1] = projectedRing[i];
    const [x2, y2] = projectedRing[(i + 1) % projectedRing.length];
    if ((y1 <= y && y2 > y) || (y2 <= y && y1 > y)) {
      xs.push(x1 + ((y - y1) / (y2 - y1)) * (x2 - x1));
    }
  }
  return xs;
}

function localWidthAtCentroid(feature, projection, centroid) {
  const geom = feature.geometry;
  const polygons = geom.type === "Polygon" ? [geom.coordinates] : geom.type === "MultiPolygon" ? geom.coordinates : [];
  const [cx, cy] = centroid;
  let crossings = [];
  for (const poly of polygons) {
    const outerRing = poly[0].map((pt) => projection(pt)); // holes not expected in this data
    crossings = crossings.concat(ringCrossingsAtY(outerRing, cy));
  }
  crossings.sort((a, b) => a - b);
  for (let i = 0; i < crossings.length - 1; i++) {
    if (crossings[i] <= cx && cx <= crossings[i + 1]) return crossings[i + 1] - crossings[i];
  }
  return null; // shouldn't happen for a well-formed ring, caller falls back to the bbox
}

// Renders one set of areas (districts, or one district's barrios) into the given <svg>.
// featureCollection: a GeoJSON FeatureCollection.
// codeProp: the property holding this feature's code ("district_code" or "barrio_code").
// colorFor(code): returns a fill color for this area (any of the 4 coloring modes).
// hasData(code): whether this area has data for the current view (drives the no-data styling).
// selectedCode: currently-selected code, drawn with a highlight stroke.
// onClick(code): called when an area is clicked.
// tooltipText(code): returns the string to show on hover.
// showLabels: whether to draw the area name centered on each shape (barrio drill-down only).
// The search box + breadcrumb float over the top-left of the map, and the timeline
// bar floats over its full-width bottom strip - keep the projected geography out of
// those zones entirely, rather than just drawing UI on top of shapes that still sit
// there (which also makes the covered part of the shape unclickable).
const MAP_MARGIN = { top: 116, right: 24, bottom: 136, left: 24 };
// The bar can be one or two rows tall depending on the map's width (its "Comparar" button wraps),
// so the bottom margin is derived from its real height: bar height + its 24px offset + a gap.
function bottomMargin() {
  const bar = document.querySelector(".timeline-bar");
  const h = bar && bar.offsetHeight ? bar.offsetHeight : 104;
  return Math.max(MAP_MARGIN.bottom, h + 32);
}

export function renderMap(svg, featureCollection, { codeProp, colorFor, hasData, selectedCode, onClick, tooltipText, showLabels = false }) {
  const width = svg.node().clientWidth || 800;
  const height = svg.node().clientHeight || 600;
  svg.attr("viewBox", `0 0 ${width} ${height}`);

  const projection = d3.geoMercator().fitExtent(
    [[MAP_MARGIN.left, MAP_MARGIN.top], [width - MAP_MARGIN.right, height - bottomMargin()]],
    featureCollection
  );
  const path = d3.geoPath(projection);

  const groups = svg.selectAll("g.area-group")
    .data(featureCollection.features, (d) => d.properties[codeProp]);

  groups.exit().remove();

  const entered = groups.enter().append("g").attr("class", "area-group");
  entered.append("path").attr("class", "area-path");
  entered.append("text").attr("class", "area-label");

  const merged = entered.merge(groups);

  merged.select("path.area-path")
    .attr("d", path)
    .attr("fill", (d) => (hasData(d.properties[codeProp]) ? colorFor(d.properties[codeProp]) : NO_DATA_COLOR))
    .classed("no-data", (d) => !hasData(d.properties[codeProp]))
    .classed("selected", (d) => d.properties[codeProp] === selectedCode)
    .on("click", (event, d) => onClick(d.properties[codeProp]))
    .on("mousemove", (event, d) => showTooltip(event, tooltipText(d.properties[codeProp])))
    .on("mouseleave", hideTooltip);

  const labelText = (d) => d.properties[codeProp === "district_code" ? "district_name" : "barrio_name"];
  const FONT_SIZE = 11;

  const labels = merged.select("text.area-label")
    .attr("x", (d) => path.centroid(d)[0])
    .attr("y", (d) => path.centroid(d)[1])
    .attr("text-anchor", "middle")
    .attr("dominant-baseline", "middle")
    .style("fill", (d) => {
      const code = d.properties[codeProp];
      return hasData(code) ? textColorFor(colorFor(code)) : "#1C1B18";
    })
    .text((d) => (showLabels ? labelText(d) : ""))
    .style("pointer-events", "none");

  // A label that overflows its own shape (common for small/narrow barrios) is worse
  // than no label - the name is still available on hover via the tooltip. Measure
  // each label against its shape's actual on-screen bounding box and blank it out
  // if it doesn't comfortably fit, rather than letting it spill over the neighbors.
  if (showLabels) {
    labels.each(function (d) {
      const centroid = path.centroid(d);
      const [[x0, y0], [x1, y1]] = path.bounds(d);
      const boxHeight = y1 - y0;
      const localWidth = localWidthAtCentroid(d, projection, centroid);
      const availableWidth = localWidth != null ? localWidth : x1 - x0;
      const textWidth = this.getComputedTextLength();
      if (textWidth > availableWidth * 0.9 || boxHeight < FONT_SIZE * 1.8) {
        d3.select(this).text("");
      }
    });
  }
}
