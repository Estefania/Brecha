#!/usr/bin/env python3
"""
Step 3 - SERPAVI rent by census section.

Downloads MIVAU's SERPAVI bulk database (tax-based, IRPF Modelo 100), which
covers every census section in Spain, 2011-2024, split by building type:
VC (vivienda colectiva, apartment buildings) and VU (vivienda unifamiliar,
single-family / rural). Filters to Madrid city (municipality 28079), reshapes
the wide per-year columns into one row per section/year/building type, and
cross-checks the section codes against data/processed/section_to_barrio.csv
from step 1.

Usage (run from the project folder):
    python pipeline/03_rent.py inspect     # download + preview sheet names and columns
    python pipeline/03_rent.py build       # filter, reshape, cross-check, write CSV

Output (data/processed/):
    rent_by_section.csv   cusec, section_code, district_code, year, building_type
                           (VC/VU), count, rent_m2_median/p25/p75,
                           rent_total_median/p25/p75, surface_median/p25/p75,
                           barrio_code, barrio_name (from step 1's join)

Rule: sections with fewer than ~10 rented dwellings are blank in the source
(secrecy threshold) and MUST stay blank here, not be imputed.
"""
from __future__ import annotations

import argparse
import re
import sys
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"

TABLE_URL = (
    "https://cdn.mivau.gob.es/portal-web-mivau/vivienda/serpavi/"
    "2026-03_09_bd_SERPAVI_2011-2024%20-%20DEFINITIVO%20WEB_v2.xlsx"
)
SHEET = "Secciones censales"
MUNI_CODE = "28079"  # Madrid city
HEADERS = {"User-Agent": "Mozilla/5.0 (brecha-madrid data pipeline)"}

# column name -> (metric, stat), for columns shaped METRIC_STAT_TYPE_YY
METRIC_STAT_RE = re.compile(r"^(ALQM2_LV|ALQTBID12|SLVM2)_(M|25|75)_(VC|VU)_(\d{2})$")
COUNT_RE = re.compile(r"^BI_ALVHEPCO_T(VC|VU)_(\d{2})$")
METRIC_NAMES = {
    "ALQM2_LV": "rent_m2",
    "ALQTBID12": "rent_total",
    "SLVM2": "surface",
}
STAT_NAMES = {"M": "median", "25": "p25", "75": "p75"}


def download(force: bool = False) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    dest = RAW / "serpavi_secciones.xlsx"
    if dest.exists() and not force:
        print(f"  already downloaded ({dest.name})")
        return dest
    print(f"  downloading {TABLE_URL}")
    try:
        req = urllib.request.Request(TABLE_URL, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=300) as resp, open(dest, "wb") as fh:
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                fh.write(chunk)
    except Exception as exc:  # noqa: BLE001
        if dest.exists():
            dest.unlink()
        sys.exit(
            f"\nCould not download the SERPAVI database: {exc}\n"
            f"Download it manually in a browser from:\n  {TABLE_URL}\n"
            f"and save it as:\n  {dest}\nthen run the command again."
        )
    return dest


def load_raw(force: bool = False) -> pd.DataFrame:
    path = download(force)
    return pd.read_excel(path, sheet_name=SHEET, engine="openpyxl")


def cmd_inspect(args: argparse.Namespace) -> None:
    print("Downloading / loading SERPAVI database (Secciones censales sheet)...")
    df = load_raw(args.force)
    print(f"\nrows: {len(df)}, columns: {len(df.columns)}")
    print("id columns:", [c for c in df.columns if c in ("CPRO", "LITPRO", "CUMUN", "LITMUN", "CUSEC")])
    print("\nsample value columns for year 23:", [c for c in df.columns if c.endswith("_23")][:12])
    madrid = df[df["CUMUN"].astype(str) == MUNI_CODE]
    print(f"\nMadrid city rows: {len(madrid)}")
    print(madrid[["CUSEC", "ALQM2_LV_M_VC_23", "ALQM2_LV_M_VU_23", "BI_ALVHEPCO_TVC_23"]].head(6).to_string(index=False))


def reshape(df: pd.DataFrame) -> pd.DataFrame:
    long_frames = []
    for btype in ("VC", "VU"):
        year_cols: dict[str, list[str]] = {}
        for col in df.columns:
            m = METRIC_STAT_RE.match(col)
            if m and m.group(3) == btype:
                metric, stat, _, yy = m.groups()
                year_cols.setdefault(yy, []).append((f"{METRIC_NAMES[metric]}_{STAT_NAMES[stat]}", col))
                continue
            m = COUNT_RE.match(col)
            if m and m.group(1) == btype:
                yy = m.group(2)
                year_cols.setdefault(yy, []).append(("count", col))
        for yy, pairs in year_cols.items():
            rename_map = {old_col: new_name for new_name, old_col in pairs}
            sub = df[["CUSEC"] + [c for _, c in pairs]].rename(columns=rename_map).copy()
            sub["cusec"] = df["CUSEC"]
            sub["year"] = 2000 + int(yy)
            sub["building_type"] = btype
            long_frames.append(sub)
    out = pd.concat(long_frames, ignore_index=True)
    value_cols = ["count", "rent_m2_median", "rent_m2_p25", "rent_m2_p75",
                  "rent_total_median", "rent_total_p25", "rent_total_p75",
                  "surface_median", "surface_p25", "surface_p75"]
    for c in value_cols:
        if c not in out.columns:
            out[c] = pd.NA
    return out[["cusec", "year", "building_type"] + value_cols]


def cmd_build(args: argparse.Namespace) -> None:
    print("Loading SERPAVI database...")
    df = load_raw(args.force)
    df["CUSEC"] = df["CUSEC"].astype(str)
    df = df[df["CUMUN"].astype(str) == MUNI_CODE].copy()
    print(f"Madrid city rows: {len(df)}")

    long_df = reshape(df)
    long_df["cusec"] = long_df["cusec"].astype(str).str.zfill(10)
    long_df["section_code"] = long_df["cusec"].str[len(MUNI_CODE):]
    long_df["district_code"] = long_df["cusec"].str[:len(MUNI_CODE) + 2]

    print(f"\nsection x year x building_type rows: {len(long_df)}")
    print(f"distinct sections: {long_df['section_code'].nunique()}")
    print(f"years: {sorted(long_df['year'].unique())}")
    for year in sorted(long_df["year"].unique()):
        vc = long_df[(long_df["year"] == year) & (long_df["building_type"] == "VC")]
        n = vc["rent_m2_median"].notna().sum()
        print(f"  {year}: {n} / {len(vc)} sections with a VC rent_m2_median (>=10 leases)")

    crosswalk_path = OUT / "section_to_barrio.csv"
    if crosswalk_path.exists():
        crosswalk = pd.read_csv(crosswalk_path, dtype=str)
        long_df = long_df.merge(crosswalk, on="section_code", how="left")
        matched = long_df["barrio_code"].notna()
        print(f"\ncross-check vs {crosswalk_path.name}:")
        print(f"  rows matched to a barrio: {matched.sum()} / {len(long_df)}")
        rent_sections = set(long_df["section_code"])
        boundary_sections = set(crosswalk["section_code"])
        only_rent = sorted(rent_sections - boundary_sections)
        only_boundary = sorted(boundary_sections - rent_sections)
        if only_rent:
            print(f"  section codes in SERPAVI data but not in boundaries: {only_rent[:10]}"
                  f"{' ...' if len(only_rent) > 10 else ''}")
        if only_boundary:
            print(f"  section codes in boundaries but not in SERPAVI data: {only_boundary[:10]}"
                  f"{' ...' if len(only_boundary) > 10 else ''}")
    else:
        print(f"\nNote: {crosswalk_path.name} not found, run 'python pipeline/01_boundaries.py check' first "
              f"to add barrio_code/barrio_name to the output.")

    OUT.mkdir(parents=True, exist_ok=True)
    cols = ["cusec", "section_code", "district_code", "year", "building_type",
            "count", "rent_m2_median", "rent_m2_p25", "rent_m2_p75",
            "rent_total_median", "rent_total_p25", "rent_total_p75",
            "surface_median", "surface_p25", "surface_p75"]
    if "barrio_code" in long_df.columns:
        cols += ["barrio_code", "barrio_name"]
    long_df = long_df[cols].sort_values(["section_code", "year", "building_type"])
    long_df.to_csv(OUT / "rent_by_section.csv", index=False, encoding="utf-8")
    print(f"\nWrote {OUT / 'rent_by_section.csv'}")


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
