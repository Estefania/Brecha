#!/usr/bin/env python3
"""
Step 8 - District-level aggregation, for the year slider.

Purchase price has a much longer official history at DISTRICT level (2007-2025,
data/processed/purchase_price_by_district.csv, from step 5) than the three-way
overlap income and rent give at BARRIO level (step 7's check). The year slider
therefore drives all three metrics together at DISTRICT level, using this
step's output; barrio-level detail from step 4 stays available outside the
slider (e.g. a barrio's own detail panel).

This mirrors step 4's barrio aggregation (household-weighted mean, blank
sections excluded rather than imputed, VC/VU rent blended by lease count
before the rollup) but groups by district instead of barrio. District code
is read directly off the section code's first 2 digits (district is baked
into the section code, unlike barrio which needs the nesting check from
step 1), so this does not depend on section_to_barrio.csv.

Usage (run from the project folder):
    python pipeline/08_district_aggregate.py build

Output (data/processed/):
    income_by_district.csv   district_code, district_name, year, the 6 income
                              indicators (household-weighted mean), n_sections,
                              n_sections_with_data, household_coverage
    rent_by_district.csv     district_code, district_name, year, rent_m2,
                              same coverage columns
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "processed"

DISTRICT_NAMES = {
    "01": "Centro", "02": "Arganzuela", "03": "Retiro", "04": "Salamanca",
    "05": "Chamartín", "06": "Tetuán", "07": "Chamberí", "08": "Fuencarral-El Pardo",
    "09": "Moncloa-Aravaca", "10": "Latina", "11": "Carabanchel", "12": "Usera",
    "13": "Puente de Vallecas", "14": "Moratalaz", "15": "Ciudad Lineal", "16": "Hortaleza",
    "17": "Villaverde", "18": "Villa de Vallecas", "19": "Vicálvaro",
    "20": "San Blas-Canillejas", "21": "Barajas",
}


def weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    mask = values.notna() & weights.notna()
    if not mask.any() or weights[mask].sum() == 0:
        return float("nan")
    return (values[mask] * weights[mask]).sum() / weights[mask].sum()


def cmd_build(args: argparse.Namespace) -> None:
    hh_path = OUT / "households_by_section.csv"
    income_path = OUT / "income_by_section.csv"
    rent_path = OUT / "rent_by_section.csv"
    for p in (hh_path, income_path, rent_path):
        if not p.exists():
            sys.exit(f"{p} not found. Run steps 2, 3 and 4 first.")

    hh = pd.read_csv(hh_path, dtype={"section_code": str})
    hh["district_code"] = hh["section_code"].str[:2]

    income = pd.read_csv(income_path, dtype={"section_code": str}).drop(
        columns=["district_code", "barrio_code", "barrio_name"], errors="ignore")
    rent = pd.read_csv(rent_path, dtype={"section_code": str}).drop(
        columns=["district_code", "barrio_code", "barrio_name"], errors="ignore")

    income_cols = ["net_income_person", "net_income_household", "gross_income_person",
                   "gross_income_household", "mean_income_cu", "median_income_cu"]
    inc = income.merge(hh[["section_code", "year", "total_hogares", "district_code"]],
                        on=["section_code", "year"], how="inner")
    rows = []
    for (district_code, year), g in inc.groupby(["district_code", "year"]):
        row = {"district_code": district_code, "district_name": DISTRICT_NAMES[district_code], "year": year,
               "n_sections": len(g),
               "n_sections_with_data": int(g["net_income_household"].notna().sum()),
               "household_coverage": g.loc[g["net_income_household"].notna(), "total_hogares"].sum() / g["total_hogares"].sum()
               if g["total_hogares"].sum() else float("nan")}
        for col in income_cols:
            row[col] = weighted_mean(g[col], g["total_hogares"])
        rows.append(row)
    income_district = pd.DataFrame(rows).sort_values(["district_code", "year"])
    income_district.to_csv(OUT / "income_by_district.csv", index=False, encoding="utf-8")
    print(f"Wrote {OUT / 'income_by_district.csv'} ({len(income_district)} rows)")

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
    rent_wide["district_code"] = rent_wide["section_code"].str[:2]
    rent_sec = rent_wide.merge(hh[["section_code", "year", "total_hogares"]],
                                on=["section_code", "year"], how="inner")
    rows = []
    for (district_code, year), g in rent_sec.groupby(["district_code", "year"]):
        coverage = (g.loc[g["rent_m2"].notna(), "total_hogares"].sum() / g["total_hogares"].sum()
                    if g["total_hogares"].sum() else float("nan"))
        rows.append({
            "district_code": district_code, "district_name": DISTRICT_NAMES[district_code], "year": year,
            "n_sections": len(g), "n_sections_with_data": int(g["rent_m2"].notna().sum()),
            "household_coverage": coverage,
            "rent_m2": weighted_mean(g["rent_m2"], g["total_hogares"]),
        })
    rent_district = pd.DataFrame(rows).sort_values(["district_code", "year"])
    rent_district.to_csv(OUT / "rent_by_district.csv", index=False, encoding="utf-8")
    print(f"Wrote {OUT / 'rent_by_district.csv'} ({len(rent_district)} rows)")

    purchase_path = OUT / "purchase_price_by_district.csv"
    if purchase_path.exists():
        purchase = pd.read_csv(purchase_path, dtype={"district_code": str})
        overlap = sorted(set(income_district["year"]) & set(rent_district["year"]) & set(purchase["year"]))
        print(f"\nincome + rent + purchase_price district-level year overlap: {overlap}")
    else:
        print(f"\nNote: {purchase_path} not found, run step 5 first to check the three-way overlap.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("build")
    p.set_defaults(fn=cmd_build)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
