#!/usr/bin/env python3
"""
Step 7 - Year-overlap check.

Answers the open question "which years do all three sources cover
(defines the usable timeline)?". Reads the barrio-level outputs from
steps 4 and 5 and reports, per year, how many of the 131 barrios have usable
data in each metric, then prints the actual intersection.

Usage (run from the project folder):
    python pipeline/07_year_overlap.py check

Output (data/processed/):
    year_overlap_report.txt
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "processed"
N_BARRIOS = 131
GOOD_COVERAGE = 0.8  # household_coverage threshold to count a barrio/year as "good", not just "any"


def cmd_check(args: argparse.Namespace) -> None:
    income = pd.read_csv(OUT / "income_by_barrio.csv")
    rent = pd.read_csv(OUT / "rent_by_barrio.csv")
    purchase_barrio = pd.read_csv(OUT / "purchase_price_by_barrio.csv")
    purchase_district = pd.read_csv(OUT / "purchase_price_by_district.csv")

    def per_year(df: pd.DataFrame, value_col: str) -> pd.DataFrame:
        rows = []
        for year, g in df.groupby("year"):
            any_data = g[value_col].notna().sum()
            good = (g[value_col].notna() & (g["household_coverage"] >= GOOD_COVERAGE)).sum()
            rows.append({"year": year, "barrios_any_data": any_data, "barrios_good_coverage": good})
        return pd.DataFrame(rows)

    income_cov = per_year(income, "net_income_household")
    rent_cov = per_year(rent, "rent_m2")

    # Purchase price has no household-weighting/coverage column (it's not rolled up
    # from sections), and it will NEVER hit 131/131 by design - the source itself
    # blanks any barrio/year with fewer than 15 registered transactions (secrecy
    # threshold), same idea as SERPAVI's <10-lease rule for rent. So "good coverage"
    # here just means "most barrios have a real price", using the same 80% bar.
    PURCHASE_GOOD = 0.8
    purchase_cov = (
        purchase_barrio.groupby("year")["price_m2_total"]
        .apply(lambda s: s.notna().sum())
        .rename("barrios_any_data").reset_index()
    )
    purchase_cov["barrios_good_coverage"] = purchase_cov["barrios_any_data"].apply(
        lambda n: n if n / N_BARRIOS >= PURCHASE_GOOD else 0)

    lines = ["YEAR-OVERLAP CHECK", f"(barrios in the boundary layer: {N_BARRIOS}, "
             f"'good coverage' = household_coverage >= {GOOD_COVERAGE:.0%} for income/rent, "
             f"or >= {PURCHASE_GOOD:.0%} of barrios non-null for purchase)", ""]

    lines.append("income_by_barrio.csv (net_income_household):")
    lines.append(income_cov.to_string(index=False))
    lines.append("")
    lines.append("rent_by_barrio.csv (rent_m2):")
    lines.append(rent_cov.to_string(index=False))
    lines.append("")
    lines.append("purchase_price_by_barrio.csv (price_m2_total, secrecy-blanked <15 transactions):")
    lines.append(purchase_cov.to_string(index=False))
    lines.append("")

    income_years_good = set(income_cov.loc[income_cov["barrios_good_coverage"] == N_BARRIOS, "year"])
    rent_years_good = set(rent_cov.loc[rent_cov["barrios_good_coverage"] == N_BARRIOS, "year"])
    purchase_years_good = set(purchase_cov.loc[purchase_cov["barrios_good_coverage"] > 0, "year"])
    both_good = sorted(income_years_good & rent_years_good)
    lines.append(f"income+rent years with ALL {N_BARRIOS} barrios at good coverage: {both_good}")
    lines.append("")

    purchase_barrio_years = sorted(purchase_barrio["year"].unique())
    purchase_district_years = sorted(purchase_district["year"].unique())
    lines.append(f"purchase_price_by_barrio.csv years: {purchase_barrio_years} "
                 f"({purchase_barrio['barrio_code'].nunique()} barrios, full 2015-2025 history)")
    lines.append(f"purchase_price_by_district.csv years: {purchase_district_years} "
                 f"({purchase_district['district_code'].nunique()} districts, no barrio detail)")
    lines.append("")

    three_way_barrio = sorted(set(both_good) & purchase_years_good)
    lines.append(f"THREE-WAY overlap at barrio level (income + rent + purchase, all barrio-level, "
                 f"'good coverage' each): {three_way_barrio if three_way_barrio else 'NONE'}")
    lines.append("")
    two_way_barrio = both_good
    lines.append(f"TWO-WAY overlap at barrio level (income + rent only): {two_way_barrio}")
    lines.append("")
    lines.append("District-level income/rent are a separate rollup (step 8), not read here; see "
                 "year_overlap_report.txt's own three-way overlap print for that level.")

    report = "\n".join(str(l) for l in lines)
    print(report)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "year_overlap_report.txt").write_text(report, encoding="utf-8")
    print(f"\nWrote {OUT / 'year_overlap_report.txt'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check")
    p.set_defaults(fn=cmd_check)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
