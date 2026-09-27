#!/usr/bin/env python3
"""
Step 2 - INE household income by census section.

Downloads INE table 31097 "Indicadores de renta media y mediana" (Atlas de
Distribucion de Renta de los Hogares), which covers the whole province of
Madrid at municipality, district and census-section level, 2015-2023.
Filters it down to Madrid city (municipality 28079), pivots it to one row
per section/year, and cross-checks the section codes against
data/processed/section_to_barrio.csv from step 1.

Usage (run from the project folder):
    python pipeline/02_income.py inspect     # download + preview raw table
    python pipeline/02_income.py build       # filter, pivot, cross-check, write CSV

Output (data/processed/):
    income_by_section.csv   cusec, section_code, district_code, year,
                             net/gross income per person/household, mean and
                             median income per consumption unit,
                             barrio_code, barrio_name (from step 1's join)
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"

TABLE_URL = "https://www.ine.es/jaxiT3/files/t/es/csv_bd/31097.csv"
MUNI_CODE = "28079"  # Madrid city
HEADERS = {"User-Agent": "Mozilla/5.0 (brecha-madrid data pipeline)"}

INDICATOR_COLS = {
    "Renta neta media por persona": "net_income_person",
    "Renta neta media por hogar": "net_income_household",
    "Renta bruta media por persona": "gross_income_person",
    "Renta bruta media por hogar": "gross_income_household",
    "Media de la renta por unidad de consumo": "mean_income_cu",
    "Mediana de la renta por unidad de consumo": "median_income_cu",
}


def download(force: bool = False) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    dest = RAW / "ine_31097_renta.csv"
    if dest.exists() and not force:
        print(f"  already downloaded ({dest.name})")
        return dest
    print(f"  downloading {TABLE_URL}")
    try:
        req = urllib.request.Request(TABLE_URL, headers=HEADERS)
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
            f"\nCould not download the INE table: {exc}\n"
            f"Download it manually in a browser from:\n  {TABLE_URL}\n"
            f"and save it as:\n  {dest}\nthen run the command again."
        )
    return dest


def load_raw(force: bool = False) -> pd.DataFrame:
    path = download(force)
    return pd.read_csv(path, sep="\t", encoding="utf-8-sig", dtype=str)


def cmd_inspect(args: argparse.Namespace) -> None:
    print("Downloading / loading INE table 31097 (Madrid province)...")
    df = load_raw(args.force)
    print(f"\nrows: {len(df)}")
    print("columns:", list(df.columns))
    print("\nindicators found:")
    for v in sorted(df.iloc[:, 3].dropna().unique()):
        print(f"  - {v}")
    print("\nyears found:", sorted(df["Periodo"].dropna().unique(), key=int))
    print("\nsample Madrid section rows:")
    madrid = df[df["Municipios"].str.startswith(MUNI_CODE + " ", na=False)]
    print(madrid[madrid["Secciones"].notna()].head(6).to_string(index=False))


def cmd_build(args: argparse.Namespace) -> None:
    print("Loading INE table...")
    df = load_raw(args.force)
    df = df[df["Municipios"].str.startswith(MUNI_CODE + " ", na=False)]
    df = df[df["Secciones"].notna()].copy()

    df["cusec"] = df["Secciones"].str.split(" ", n=1).str[0]
    df["section_code"] = df["cusec"].str[len(MUNI_CODE):]
    df["district_code"] = df["Distritos"].str.split(" ", n=1).str[0]
    df["indicator"] = df.iloc[:, 3].map(INDICATOR_COLS)
    unmapped = df.loc[df["indicator"].isna(), df.columns[3]].unique()
    if len(unmapped):
        sys.exit(f"Unknown indicator(s) in the source table, update INDICATOR_COLS: {list(unmapped)}")
    df["year"] = df["Periodo"].astype(int)
    df["value"] = pd.to_numeric(df["Total"].str.replace(".", "", regex=False), errors="coerce")

    wide = df.pivot_table(
        index=["cusec", "section_code", "district_code", "year"],
        columns="indicator",
        values="value",
        aggfunc="first",
    ).reset_index()
    wide.columns.name = None
    for col in INDICATOR_COLS.values():
        if col not in wide.columns:
            wide[col] = pd.NA

    print(f"sections x years rows: {len(wide)}")
    print(f"distinct sections: {wide['section_code'].nunique()}")
    print(f"years: {sorted(wide['year'].unique())}")
    for year in sorted(wide["year"].unique()):
        n = wide.loc[wide["year"] == year, "net_income_household"].notna().sum()
        print(f"  {year}: {n} sections with net_income_household")

    crosswalk_path = OUT / "section_to_barrio.csv"
    if crosswalk_path.exists():
        crosswalk = pd.read_csv(crosswalk_path, dtype=str)
        wide = wide.merge(crosswalk, on="section_code", how="left")
        matched = wide["barrio_code"].notna()
        print(f"\ncross-check vs {crosswalk_path.name}:")
        print(f"  income rows matched to a barrio: {matched.sum()} / {len(wide)}")
        income_sections = set(wide["section_code"])
        boundary_sections = set(crosswalk["section_code"])
        only_income = sorted(income_sections - boundary_sections)
        only_boundary = sorted(boundary_sections - income_sections)
        if only_income:
            print(f"  section codes in INE data but not in boundaries: {only_income[:10]}"
                  f"{' ...' if len(only_income) > 10 else ''}")
        if only_boundary:
            print(f"  section codes in boundaries but not in INE data: {only_boundary[:10]}"
                  f"{' ...' if len(only_boundary) > 10 else ''}")
    else:
        print(f"\nNote: {crosswalk_path.name} not found, run 'python pipeline/01_boundaries.py check' first "
              f"to add barrio_code/barrio_name to the output.")

    OUT.mkdir(parents=True, exist_ok=True)
    cols = ["cusec", "section_code", "district_code", "year"] + list(INDICATOR_COLS.values())
    if "barrio_code" in wide.columns:
        cols += ["barrio_code", "barrio_name"]
    wide = wide[cols].sort_values(["section_code", "year"])
    wide.to_csv(OUT / "income_by_section.csv", index=False, encoding="utf-8")
    print(f"\nWrote {OUT / 'income_by_section.csv'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, fn in (("inspect", cmd_inspect), ("build", cmd_build)):
        p = sub.add_parser(name)
        p.add_argument("--force", action="store_true", help="download again even if the file exists")
        p.set_defaults(fn=fn)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
