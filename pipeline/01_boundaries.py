#!/usr/bin/env python3
"""
Step 1 - Madrid boundaries.

Downloads the official district, barrio and census-section layers from the
Ayuntamiento de Madrid Geoportal and checks whether census sections nest
inside barrios (needed to build barrio-level income and rent from sections).

Usage (run from the project folder):
    python pipeline/01_boundaries.py inspect      # download + print columns, CRS, sample rows
    python pipeline/01_boundaries.py check        # nesting check + section->barrio table
    python pipeline/01_boundaries.py check --export-geojson

If auto-detection of a column fails, pass it explicitly, e.g.:
    python pipeline/01_boundaries.py check --section-col CUSEC --barrio-col COD_BAR --barrio-name-col NOMBRE

Outputs (data/processed/):
    section_to_barrio.csv   section_code, barrio_code, barrio_name, share
    nesting_report.txt      summary of the check
    distritos.geojson, barrios.geojson   (only with --export-geojson; WGS84, simplified)
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"

BASE = "https://geoportal.madrid.es/fsdescargas/IDEAM_WBGEOPORTAL/LIMITES_ADMINISTRATIVOS"
LAYERS = {
    "distritos": f"{BASE}/Distritos/Distritos.zip",
    "barrios": f"{BASE}/Barrios/Barrios.zip",
    "secciones": f"{BASE}/Seccionado/Secciones_Censales.zip",
}
EXPECTED = {"distritos": 21, "barrios": 131}
METRIC_CRS = "EPSG:25830"  # ETRS89 / UTM zone 30N (metres) - areas are computed here
HEADERS = {"User-Agent": "Mozilla/5.0 (brecha-madrid data pipeline)"}


# ----------------------------------------------------------------------------
# Download and load
# ----------------------------------------------------------------------------
def download(name: str, force: bool = False) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    dest = RAW / f"{name}.zip"
    if dest.exists() and not force:
        print(f"  {name}: already downloaded ({dest.name})")
        return dest
    url = LAYERS[name]
    print(f"  {name}: downloading {url}")
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=180) as resp, open(dest, "wb") as fh:
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                fh.write(chunk)
    except Exception as exc:  # noqa: BLE001
        if dest.exists():
            dest.unlink()
        sys.exit(
            f"\nCould not download {name}: {exc}\n"
            f"Download it manually in a browser from:\n  {url}\n"
            f"and save it as:\n  {dest}\nthen run the command again."
        )
    return dest


def load(name: str, encoding: str | None, force: bool = False) -> gpd.GeoDataFrame:
    zpath = download(name, force)
    folder = RAW / name
    if not list(folder.rglob("*.shp")):
        folder.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zpath) as zf:
            zf.extractall(folder)
    shps = sorted(folder.rglob("*.shp"), key=lambda p: p.stat().st_size, reverse=True)
    if not shps:
        sys.exit(f"No .shp file found inside {zpath}")
    if len(shps) > 1:
        print(f"  {name}: several shapefiles found, using the largest: {shps[0].name}")
    kwargs = {"encoding": encoding} if encoding else {}
    gdf = gpd.read_file(shps[0], **kwargs)
    if gdf.crs is None:
        print(f"  WARNING: {name} has no CRS; assuming {METRIC_CRS}")
        gdf = gdf.set_crs(METRIC_CRS)
    return gdf


# ----------------------------------------------------------------------------
# Column detection (field names are not documented in the pages I checked,
# so we guess from the names and let you override with --*-col)
# ----------------------------------------------------------------------------
def find_col(gdf: gpd.GeoDataFrame, explicit: str | None, patterns: list[list[str]]) -> str | None:
    cols = [c for c in gdf.columns if c != "geometry"]
    if explicit:
        if explicit not in cols:
            sys.exit(f"Column '{explicit}' not found. Available: {cols}")
        return explicit
    lower = {c: c.lower() for c in cols}
    for keywords in patterns:  # each pattern = all keywords must appear
        for c in cols:
            if all(k in lower[c] for k in keywords):
                return c
    return None


# ----------------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------------
def cmd_inspect(args: argparse.Namespace) -> None:
    print("Downloading / loading layers...")
    for name in LAYERS:
        gdf = load(name, args.encoding, args.force)
        print(f"\n=== {name.upper()} ===")
        print(f"rows: {len(gdf)}" + (f" (expected {EXPECTED[name]})" if name in EXPECTED else ""))
        print(f"CRS: {gdf.crs}")
        print("columns:")
        for c in gdf.columns:
            if c != "geometry":
                print(f"  - {c}  [{gdf[c].dtype}]  e.g. {gdf[c].iloc[0]!r}")
        print("first rows:")
        print(gdf.drop(columns="geometry").head(3).to_string())
    print("\nCopy this whole output back to me if a column looks odd (accents, codes).")


def cmd_check(args: argparse.Namespace) -> None:
    print("Loading layers...")
    sec = load("secciones", args.encoding, args.force)
    bar = load("barrios", args.encoding, args.force)
    dis = load("distritos", args.encoding, args.force)

    sec_col = find_col(sec, args.section_col, [["cusec"], ["sec", "cod"], ["sec", "id"], ["seccion"], ["sec"]])
    bar_code = find_col(bar, args.barrio_col, [["bar", "cod"], ["bar", "id"], ["codbar"], ["cod"]])
    bar_name = find_col(bar, args.barrio_name_col, [["bar", "nom"], ["nombre"], ["nom"]])
    missing = [n for n, v in [("--section-col", sec_col), ("--barrio-col", bar_code), ("--barrio-name-col", bar_name)] if v is None]
    if missing:
        sys.exit(f"Could not auto-detect: {', '.join(missing)}. Run 'inspect' and pass them explicitly.")
    print(f"  using: sections='{sec_col}', barrio code='{bar_code}', barrio name='{bar_name}'")

    # Project to metres and repair geometries
    sec = sec.to_crs(METRIC_CRS)
    bar = bar.to_crs(METRIC_CRS)
    dis = dis.to_crs(METRIC_CRS)
    for g in (sec, bar, dis):
        g["geometry"] = g.geometry.make_valid()

    sec[sec_col] = sec[sec_col].astype(str).str.strip()
    sec = sec[[sec_col, "geometry"]].dissolve(by=sec_col, as_index=False)
    sec["sec_area"] = sec.geometry.area
    bar = bar[[bar_code, bar_name, "geometry"]].rename(columns={bar_code: "barrio_code", bar_name: "barrio_name"})
    dis = dis[["COD_DIS", "NOMBRE", "geometry"]].rename(columns={"COD_DIS": "district_code", "NOMBRE": "district_name"})
    bar["barrio_code"] = bar["barrio_code"].astype(str).str.strip()
    # Unlike COD_BAR (already text in the shapefile), COD_DIS is numeric, so districts 1-9
    # lose their leading zero on a plain astype(str) - zfill back to the 2-digit convention
    # used everywhere else in this pipeline (income_by_district.csv, barrio_code prefixes, etc).
    dis["district_code"] = dis["district_code"].astype(str).str.strip().str.zfill(2)

    ov = gpd.overlay(sec, bar, how="intersection", keep_geom_type=True)
    ov["ov_area"] = ov.geometry.area
    ov["share"] = ov["ov_area"] / ov["sec_area"]

    best = ov.sort_values("ov_area", ascending=False).drop_duplicates(sec_col).copy()
    touches = ov[ov["share"] > 0.01].groupby(sec_col).size()
    best["n_barrios_touched"] = best[sec_col].map(touches).fillna(1).astype(int)
    no_barrio = sorted(set(sec[sec_col]) - set(best[sec_col]))

    clean = int((best["share"] >= 0.99).sum())
    minor = int(((best["share"] >= 0.90) & (best["share"] < 0.99)).sum())
    straddle = int((best["share"] < 0.90).sum())
    barrios_without_sections = sorted(set(bar["barrio_code"]) - set(best["barrio_code"]))

    lines = [
        "NESTING CHECK: census sections inside barrios",
        f"districts found: {len(dis)} (expected {EXPECTED['distritos']})",
        f"barrios found:   {len(bar)} (expected {EXPECTED['barrios']})",
        f"sections found:  {len(sec)}",
        "",
        f"sections >=99% inside one barrio : {clean}",
        f"sections 90-99% inside one barrio: {minor}",
        f"sections <90% inside one barrio  : {straddle}   <-- these straddle barrios",
        f"sections touching >1 barrio (>1% of area): {int((best['n_barrios_touched'] > 1).sum())}",
        f"sections with no barrio at all   : {len(no_barrio)}",
        f"barrios with no section          : {len(barrios_without_sections)}",
        "",
        f"area covered: sections {sec['sec_area'].sum() / 1e6:.1f} km2 vs barrios {bar.geometry.area.sum() / 1e6:.1f} km2",
        "",
        "10 worst sections (lowest share in their main barrio):",
        best.sort_values("share").head(10)[[sec_col, "barrio_name", "share", "n_barrios_touched"]].to_string(index=False),
    ]
    report = "\n".join(lines)
    print("\n" + report)

    OUT.mkdir(parents=True, exist_ok=True)
    table = best[[sec_col, "barrio_code", "barrio_name", "share"]].rename(columns={sec_col: "section_code"})
    table.sort_values("section_code").to_csv(OUT / "section_to_barrio.csv", index=False, encoding="utf-8")
    (OUT / "nesting_report.txt").write_text(report, encoding="utf-8")
    print(f"\nWrote {OUT / 'section_to_barrio.csv'} and {OUT / 'nesting_report.txt'}")

    if args.export_geojson:
        for name, g in (("distritos", dis), ("barrios", bar)):
            simple = g.copy()
            simple["geometry"] = simple.geometry.simplify(3, preserve_topology=True)
            simple.to_crs("EPSG:4326").to_file(OUT / f"{name}.geojson", driver="GeoJSON")
            print(f"Wrote {OUT / (name + '.geojson')}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, fn in (("inspect", cmd_inspect), ("check", cmd_check)):
        p = sub.add_parser(name)
        p.add_argument("--force", action="store_true", help="download again even if the zip exists")
        p.add_argument("--encoding", default=None, help="shapefile text encoding if accents look wrong, e.g. cp1252 or utf-8")
        if name == "check":
            p.add_argument("--section-col")
            p.add_argument("--barrio-col")
            p.add_argument("--barrio-name-col")
            p.add_argument("--export-geojson", action="store_true")
        p.set_defaults(fn=fn)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
