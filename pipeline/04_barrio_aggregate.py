#!/usr/bin/env python3
"""
Step 4 - Households by section, and barrio-level aggregation.

Part A downloads the Ayuntamiento de Madrid's "Hogares por tamano... segun
distrito" series (one xlsx/xls file per year, Padron municipal, 2015-2023)
and extracts households and population per census section - the weights used
to roll sections up into barrios.

Part B combines those weights with data/processed/income_by_section.csv and
rent_by_section.csv (from steps 2 and 3) and section_to_barrio.csv (step 1)
to produce barrio-level income and rent, weighted by number of households,
by design: barrio figures are CALCULATED
from sections, not looked up from an official barrio table, and blank
sections are excluded from the average rather than imputed.

Usage (run from the project folder):
    python pipeline/04_barrio_aggregate.py inspect   # download + preview one year
    python pipeline/04_barrio_aggregate.py build     # fetch all years, aggregate, write CSVs

Output (data/processed/):
    households_by_section.csv   section_code, year, habitantes, total_hogares, avg_household_size
    income_by_barrio.csv        barrio_code, barrio_name, year, the 6 income indicators
                                 (household-weighted mean), n_sections, n_sections_with_data,
                                 household_coverage (share of the barrio's households in
                                 sections that had data)
    rent_by_barrio.csv          barrio_code, barrio_name, year, rent_m2 (household-weighted
                                 mean of each section's VC/VU-blended rent_m2), same coverage
                                 columns
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

DATASET_BASE = "https://datos.madrid.es/dataset/300438-0-hogares-tamano/resource"
# year -> resource slug (id-N-hogares-tamano-EXT); found on the dataset's downloads page
RESOURCES = {
    2015: "300438-9-hogares-tamano-xls",
    2016: "300438-8-hogares-tamano-xls",
    2017: "300438-16-hogares-tamano-xls",
    2018: "300438-7-hogares-tamano-xls",
    2019: "300438-5-hogares-tamano-xls",
    2020: "300438-6-hogares-tamano-xls",
    2021: "300438-4-hogares-tamano-xls",
    2022: "300438-0-hogares-tamano-xlsx",
    2023: "300438-1-hogares-tamano-xlsx",
    2024: "300438-3-hogares-tamano-xlsx",
}
SHEET = "Tamaño del hogar"
HEADERS = {"User-Agent": "Mozilla/5.0 (brecha-madrid data pipeline)"}


def download(year: int, force: bool = False) -> Path:
    slug = RESOURCES[year]
    ext = slug.rsplit("-", 1)[-1]
    RAW.mkdir(parents=True, exist_ok=True)
    dest = RAW / f"hogares_{year}.{ext}"
    if dest.exists() and not force:
        print(f"  {year}: already downloaded ({dest.name})")
        return dest
    url = f"{DATASET_BASE}/{slug}/download/{slug}.{ext}"
    print(f"  {year}: downloading {url}")
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
            f"\nCould not download the {year} households file: {exc}\n"
            f"Download it manually in a browser from:\n  {url}\n"
            f"and save it as:\n  {dest}\nthen run the command again."
        )
    return dest


def parse_year(year: int, force: bool = False) -> pd.DataFrame:
    path = download(year, force)
    raw = pd.read_excel(path, sheet_name=SHEET, header=None)
    rows = raw[raw[1].notna()]
    section_code = rows[1].apply(lambda v: str(int(v)).zfill(5) if not isinstance(v, str) else v.strip().zfill(5))
    out = pd.DataFrame({
        "section_code": section_code,
        "year": year,
        "habitantes": pd.to_numeric(rows[2], errors="coerce"),
        "total_hogares": pd.to_numeric(rows[3], errors="coerce"),
        "avg_household_size": pd.to_numeric(rows[4], errors="coerce"),
    })
    return out


def cmd_inspect(args: argparse.Namespace) -> None:
    year = args.year or max(RESOURCES)
    print(f"Downloading / loading households file for {year}...")
    df = parse_year(year, args.force)
    print(f"\nsection rows: {len(df)}")
    print(f"total habitantes: {df['habitantes'].sum():,.0f}")
    print(f"total hogares: {df['total_hogares'].sum():,.0f}")
    print(df.head(6).to_string(index=False))


def load_all_households(force: bool = False) -> pd.DataFrame:
    frames = [parse_year(year, force) for year in sorted(RESOURCES)]
    return pd.concat(frames, ignore_index=True)


def weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    mask = values.notna() & weights.notna()
    if not mask.any() or weights[mask].sum() == 0:
        return float("nan")
    return (values[mask] * weights[mask]).sum() / weights[mask].sum()


def cmd_build(args: argparse.Namespace) -> None:
    print("Downloading / parsing households by section, 2015-2023...")
    hh = load_all_households(args.force)
    OUT.mkdir(parents=True, exist_ok=True)
    hh.sort_values(["section_code", "year"]).to_csv(OUT / "households_by_section.csv", index=False, encoding="utf-8")
    print(f"Wrote {OUT / 'households_by_section.csv'} ({len(hh)} rows)")

    crosswalk_path = OUT / "section_to_barrio.csv"
    if not crosswalk_path.exists():
        sys.exit(f"{crosswalk_path} not found. Run 'python pipeline/01_boundaries.py check' first.")
    crosswalk = pd.read_csv(crosswalk_path, dtype={"section_code": str, "barrio_code": str})[["section_code", "barrio_code", "barrio_name"]]

    income_path = OUT / "income_by_section.csv"
    rent_path = OUT / "rent_by_section.csv"
    if not income_path.exists() or not rent_path.exists():
        sys.exit("income_by_section.csv / rent_by_section.csv not found. Run steps 2 and 3 first.")

    income = pd.read_csv(income_path, dtype={"section_code": str}).drop(columns=["barrio_code", "barrio_name"], errors="ignore")
    rent = pd.read_csv(rent_path, dtype={"section_code": str}).drop(columns=["barrio_code", "barrio_name"], errors="ignore")

    hh_sec = hh.merge(crosswalk, on="section_code", how="inner")

    # --- income: household-weighted mean of each section indicator, per barrio/year ---
    income_cols = ["net_income_person", "net_income_household", "gross_income_person",
                   "gross_income_household", "mean_income_cu", "median_income_cu"]
    inc = income.merge(hh_sec[["section_code", "year", "total_hogares", "barrio_code", "barrio_name"]],
                        on=["section_code", "year"], how="inner")
    rows = []
    for (barrio_code, barrio_name, year), g in inc.groupby(["barrio_code", "barrio_name", "year"]):
        row = {"barrio_code": barrio_code, "barrio_name": barrio_name, "year": year,
               "n_sections": len(g),
               "n_sections_with_data": int(g["net_income_household"].notna().sum()),
               "household_coverage": g.loc[g["net_income_household"].notna(), "total_hogares"].sum() / g["total_hogares"].sum()
               if g["total_hogares"].sum() else float("nan")}
        for col in income_cols:
            row[col] = weighted_mean(g[col], g["total_hogares"])
        rows.append(row)
    income_barrio = pd.DataFrame(rows).sort_values(["barrio_code", "year"])
    income_barrio.to_csv(OUT / "income_by_barrio.csv", index=False, encoding="utf-8")
    print(f"Wrote {OUT / 'income_by_barrio.csv'} ({len(income_barrio)} rows)")

    # --- rent: blend VC/VU per section (weighted by lease count), then household-weight across sections ---
    rent_wide = rent.pivot_table(index=["section_code", "year"], columns="building_type",
                                  values=["rent_m2_median", "count"], aggfunc="first").reset_index()
    rent_wide.columns = ["_".join(c).strip("_") if isinstance(c, tuple) else c for c in rent_wide.columns]
    for col in ["rent_m2_median_VC", "rent_m2_median_VU", "count_VC", "count_VU"]:
        if col not in rent_wide.columns:
            rent_wide[col] = pd.NA

    def blend_rent(row: pd.Series) -> float:
        vals = [(row["rent_m2_median_VC"], row["count_VC"]), (row["rent_m2_median_VU"], row["count_VU"])]
        vals = [(v, w) for v, w in vals if pd.notna(v) and pd.notna(w) and w > 0]
        if not vals:
            return float("nan")
        total_w = sum(w for _, w in vals)
        return sum(v * w for v, w in vals) / total_w

    rent_wide["rent_m2"] = rent_wide.apply(blend_rent, axis=1)
    rent_sec = rent_wide.merge(hh_sec[["section_code", "year", "total_hogares", "barrio_code", "barrio_name"]],
                                on=["section_code", "year"], how="inner")
    rows = []
    for (barrio_code, barrio_name, year), g in rent_sec.groupby(["barrio_code", "barrio_name", "year"]):
        coverage = (g.loc[g["rent_m2"].notna(), "total_hogares"].sum() / g["total_hogares"].sum()
                    if g["total_hogares"].sum() else float("nan"))
        rows.append({
            "barrio_code": barrio_code, "barrio_name": barrio_name, "year": year,
            "n_sections": len(g), "n_sections_with_data": int(g["rent_m2"].notna().sum()),
            "household_coverage": coverage,
            "rent_m2": weighted_mean(g["rent_m2"], g["total_hogares"]),
        })
    rent_barrio = pd.DataFrame(rows).sort_values(["barrio_code", "year"])
    rent_barrio.to_csv(OUT / "rent_by_barrio.csv", index=False, encoding="utf-8")
    print(f"Wrote {OUT / 'rent_by_barrio.csv'} ({len(rent_barrio)} rows)")

    print("\nincome_by_barrio.csv, latest year, lowest household_coverage:")
    latest = income_barrio[income_barrio["year"] == income_barrio["year"].max()]
    print(latest.sort_values("household_coverage").head(5)[
        ["barrio_name", "year", "household_coverage", "net_income_household"]].to_string(index=False))
    print("\nrent_by_barrio.csv, latest year, lowest household_coverage:")
    latest_r = rent_barrio[rent_barrio["year"] == rent_barrio["year"].max()]
    print(latest_r.sort_values("household_coverage").head(5)[
        ["barrio_name", "year", "household_coverage", "rent_m2"]].to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("inspect")
    p.add_argument("--force", action="store_true")
    p.add_argument("--year", type=int, choices=sorted(RESOURCES))
    p.set_defaults(fn=cmd_inspect)
    p = sub.add_parser("build")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_build)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
