#!/usr/bin/env python3
"""
Step 5 - Madrid registry purchase prices.

Two sources, at two different territorial levels:

1. Barrio level, FULL HISTORY 2015-2025: the Ayuntamiento's interactive
   "Banco de Datos" tool (series 0504020100060,
   https://servpub.madrid.es/CSEBD_WBINTER/seleccionSerie.html?numSerie=0504020100060),
   which covers "Precio medio declarado de la vivienda (euros/m2) por
   Distrito y Barrio segun Tipo de vivienda" for 2007-2025. Earlier attempts
   at this tool found its "Generar Excel/CSV" buttons unresponsive in a real
   browser and assumed the tool was simply broken. It isn't: it's a classic
   JSP pivot-table app driven by session state, not a page with a normal
   export link. Reverse-engineered access sequence (see the tool's own
   pages, no public API docs exist):
     a. GET seleccionSerie.html?numSerie=0504020100060 with a fresh cookie
        jar - the page's inline <script> blocks define every selectable
        `variable` (dimension) and `valor` (value) as JS object literals
        (e.g. `new variable("186", "Distrito", ...)`, `new valor("650021",
        "011. Palacio", ...)`). This must be fetched with a real HTTP
        client that returns the raw HTML (a JS-stripping fetcher will not
        see these) to read off the dimension/value IDs needed below.
     b. GET setearFiltroS.html and setearFiltroValor.html (repeated per
        dimension) against the session established in (a), to select:
        all districts, all 131 individual barrios (excluding the
        district-subtotal "valor" entries, which are flagged separately
        from real barrios), years 2015-2025, "Euros/m2" (not the absolute
        total dimension), and ONE vivienda-type (Total, Nueva or Usada) at
        a time - selecting all three vivienda types in one request 500'd
        server-side even at a scale (1441 cells) well under what a single
        request handled fine for one type, so this must be done as three
        separate requests/exports, one per type.
     c. POST detalleSerie.html with generarCsv=generarCsv against that same
        session. The unfiltered/"complete" export (generarExcelCompleto)
        504-timed-out - it appears to mean "every series nationwide", not
        just the filtered selection - so use the scoped generarCsv export
        instead, which returns just the selected cells.
   This produced three real CSVs (2015-2025 x 131 barrios x Total/Nueva/
   Usada), saved locally to data/raw/banco_datos_precio_barrio_{total,nuevas,
   usadas}.csv. Cross-validated exactly against the old single-year
   E3210626.xlsx snapshot this project used before (Palacio 2025: Total
   6895.15, Nuevas 6421.28, Usadas 6954.58 - all match). This closes the
   long-standing "no scriptable historical source at barrio level" gap.
   NOT automated as a pipeline download step: the session/cookie flow above
   is fragile (JSESSIONID + Akamai bot-management cookies, an undiagnosed
   500 on combined-type requests) and not worth re-running on every
   pipeline execution. A manually fetched raw source, saved locally to
   data/raw/ (see steps a-c above) - NOT committed to this repo, since the
   underlying data is Colegio de Registradores' and their own terms don't
   clearly permit redistributing it; fetch your own copy under your own use
   of their site. Re-fetch by hand and replace the three CSVs when the Banco
   de Datos tool publishes a new year.
2. District level, FULL OFFICIAL HISTORY 2007-2025, same tool and same
   Colegio de Registradores source: the "Barrio" dimension of the same series
   also holds one district-subtotal entry per district ("01. Centro", ...),
   so repeating steps a-c above but selecting those subtotal entries (instead
   of the 131 individual barrios) and years 2007-2025 returns the OFFICIAL
   district figures, complete for all 21 districts x 19 years x Total/Nueva/
   Usada (saved locally to data/raw/banco_datos_precio_distrito_{total,nuevas,
   usadas}.csv - same licensing caveat as the barrio files above, not
   committed to this repo). This REPLACED two earlier, worse approaches:
   - the Anuario Estadistico 2023 (ch. 8) transcription, which stopped at 2022
     AND turned out to be wrong for 2022: its 2022 "new" column equals the
     official TOTAL price (e.g. Centro 5,466 in both) for 20 of 21 districts
     (audit finding), and its "used" column was Idealista ASKING prices;
   - a household-weighted rollup of the barrio data (validated against the
     official figures at a median error of ~1% for total/used and 4-9% for new,
     but an estimate nonetheless, and blank/unreliable where few barrios had
     data). Both are gone; every district figure is now official ("registro").
   Barrio-level data only exists from 2016 (the registry publishes no barrio
   prices before that - verified: the 2007-2015 barrio export is entirely
   blank), so district history is much longer than barrio history.
   The district CSV keeps 2007-2025; 10_export_json.py only exports 2015+ to
   the site because income (2015+) limits every effort comparison.

Usage (run from the project folder):
    python pipeline/05_purchase.py inspect   # preview the parsed barrio history
    python pipeline/05_purchase.py build     # write both output CSVs

Output (data/processed/):
    purchase_price_by_barrio.csv     barrio_code, barrio_name, district_code,
                                      year (2015-2025), price_m2_total/new/used
    purchase_price_by_district.csv   district_code, district_name, year
                                      (2007-2025), type ("total"/"new"/"used"),
                                      price_m2, source ("registro", all rows)
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"

BANCO_DATOS_FILES = {
    "total": RAW / "banco_datos_precio_barrio_total.csv",
    "new": RAW / "banco_datos_precio_barrio_nuevas.csv",
    "used": RAW / "banco_datos_precio_barrio_usadas.csv",
}
BANCO_DATOS_YEARS = list(range(2015, 2026))
BANCO_DATOS_HEADER_LINES = 8  # 5 title lines + year row + unit row + type row
BANCO_DATOS_DATA_ROWS = 131  # one per barrio; footer (blank lines + Fuente/Observaciones) excluded via nrows

DISTRICT_FILES = {
    "total": RAW / "banco_datos_precio_distrito_total.csv",
    "new": RAW / "banco_datos_precio_distrito_nuevas.csv",
    "used": RAW / "banco_datos_precio_distrito_usadas.csv",
}
DISTRICT_YEARS = list(range(2007, 2026))

DISTRICT_NAMES = {
    "01": "Centro", "02": "Arganzuela", "03": "Retiro", "04": "Salamanca",
    "05": "Chamartín", "06": "Tetuán", "07": "Chamberí", "08": "Fuencarral-El Pardo",
    "09": "Moncloa-Aravaca", "10": "Latina", "11": "Carabanchel", "12": "Usera",
    "13": "Puente de Vallecas", "14": "Moratalaz", "15": "Ciudad Lineal", "16": "Hortaleza",
    "17": "Villaverde", "18": "Villa de Vallecas", "19": "Vicálvaro",
    "20": "San Blas-Canillejas", "21": "Barajas",
}

ROW_RE = re.compile(r"^(\d{2,3})\.\s*(.+)$")


def parse_banco_datos_file(path: Path) -> pd.DataFrame:
    """Parse one Banco de Datos export (one vivienda-type) into long form:
    barrio_code, barrio_name, district_code, year, price_m2."""
    if not path.exists():
        sys.exit(
            f"{path} not found. This is a manually-fetched checked-in raw source "
            f"(see the reverse-engineered access sequence in this script's docstring) - "
            f"it should be committed to the repo, not regenerated on every run."
        )
    df = pd.read_csv(
        path,
        sep=";",
        skiprows=BANCO_DATOS_HEADER_LINES,
        nrows=BANCO_DATOS_DATA_ROWS,
        header=None,
        names=["district_label", "barrio_label", *[str(y) for y in BANCO_DATOS_YEARS]],
        decimal=",",
        thousands=".",
        na_values=["..", ""],
        encoding="utf-8",
    )
    rows = []
    for _, r in df.iterrows():
        dm = ROW_RE.match(str(r["district_label"]).strip())
        bm = ROW_RE.match(str(r["barrio_label"]).strip())
        if not dm or not bm:
            continue
        district_code = dm.group(1)
        barrio_code = bm.group(1)
        barrio_name = bm.group(2).strip()
        for year in BANCO_DATOS_YEARS:
            v = r[str(year)]
            rows.append({
                "barrio_code": barrio_code,
                "barrio_name": barrio_name,
                "district_code": district_code,
                "year": year,
                "price_m2": pd.NA if pd.isna(v) or v == 0 else v,
            })
    return pd.DataFrame(rows)


def build_barrio_history() -> pd.DataFrame:
    merged = None
    for kind, path in BANCO_DATOS_FILES.items():
        parsed = parse_banco_datos_file(path).rename(columns={"price_m2": f"price_m2_{kind}"})
        if merged is None:
            merged = parsed
        else:
            merged = merged.merge(
                parsed[["barrio_code", "year", f"price_m2_{kind}"]],
                on=["barrio_code", "year"], how="outer",
            )
    return merged[[
        "barrio_code", "barrio_name", "district_code", "year",
        "price_m2_total", "price_m2_new", "price_m2_used",
    ]].sort_values(["barrio_code", "year"])


def parse_district_file(path: Path) -> pd.DataFrame:
    """Parse one district-level Banco de Datos export (one vivienda-type) into long
    form: district_code, district_name, year, price_m2. Rows look like
    `01. Centro;01. Centro;"4.798,92";...`; `..` (secrecy) and `0` are blank."""
    if not path.exists():
        sys.exit(f"{path} not found (manually-fetched raw source, should be in the repo).")
    rows = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        m = re.match(r"^(\d\d)\. ([^;]+);\d\d\. [^;]+;(.*)$", line)
        if not m:
            continue
        cells = next(csv.reader([m.group(3)], delimiter=";", quotechar='"'))
        if len(cells) != len(DISTRICT_YEARS):
            sys.exit(f"{path}: district {m.group(1)} has {len(cells)} cells, expected {len(DISTRICT_YEARS)}")
        for year, cell in zip(DISTRICT_YEARS, cells):
            cell = cell.strip()
            value = None if cell in ("..", "", "0", "-") else float(cell.replace(".", "").replace(",", "."))
            rows.append({"district_code": m.group(1), "district_name": DISTRICT_NAMES[m.group(1)],
                         "year": year, "price_m2": value})
    return pd.DataFrame(rows)


def build_district_history() -> pd.DataFrame:
    frames = [parse_district_file(path).assign(type=kind, source="registro")
              for kind, path in DISTRICT_FILES.items()]
    out = pd.concat(frames, ignore_index=True)
    if out["district_code"].nunique() != 21:
        sys.exit(f"expected 21 districts, parsed {out['district_code'].nunique()}")
    return out[["district_code", "district_name", "year", "type", "price_m2", "source"]]


def cmd_inspect(args: argparse.Namespace) -> None:
    df = build_barrio_history()
    print(f"barrio-year rows: {len(df)} ({df['barrio_code'].nunique()} barrios x {df['year'].nunique()} years)")
    print(f"years: {sorted(df['year'].unique())}")
    print(df[df["barrio_code"] == "011"].to_string(index=False))
    coverage = df.groupby("year")[["price_m2_total", "price_m2_new", "price_m2_used"]].apply(
        lambda g: g.notna().sum())
    print("\nnon-null barrios per year, per type:")
    print(coverage.to_string())


def cmd_build(args: argparse.Namespace) -> None:
    print("Parsing barrio purchase price history (Banco de Datos, 2015-2025)...")
    barrio = build_barrio_history()
    OUT.mkdir(parents=True, exist_ok=True)
    barrio.to_csv(OUT / "purchase_price_by_barrio.csv", index=False, encoding="utf-8")
    print(f"Wrote {OUT / 'purchase_price_by_barrio.csv'} "
          f"({len(barrio)} rows, {barrio['barrio_code'].nunique()} barrios, "
          f"years {barrio['year'].min()}-{barrio['year'].max()})")

    crosswalk_path = OUT / "section_to_barrio.csv"
    if crosswalk_path.exists():
        crosswalk_barrios = set(pd.read_csv(crosswalk_path, dtype=str)["barrio_code"])
        parsed_barrios = set(barrio["barrio_code"])
        missing = sorted(crosswalk_barrios - parsed_barrios)
        extra = sorted(parsed_barrios - crosswalk_barrios)
        print(f"cross-check vs section_to_barrio.csv: {len(crosswalk_barrios) - len(missing)} / {len(crosswalk_barrios)} barrios matched")
        if missing:
            print(f"  barrios with no purchase price rows: {missing}")
        if extra:
            print(f"  price rows with no matching barrio: {extra}")

    district = build_district_history()
    district.sort_values(["district_code", "year", "type"]).to_csv(
        OUT / "purchase_price_by_district.csv", index=False, encoding="utf-8")
    print(f"Wrote {OUT / 'purchase_price_by_district.csv'} ({len(district)} rows, "
          f"{district['district_code'].nunique()} districts, years "
          f"{district['year'].min()}-{district['year'].max()}, all official 'registro')")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, fn in (("inspect", cmd_inspect), ("build", cmd_build)):
        p = sub.add_parser(name)
        p.set_defaults(fn=fn)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
