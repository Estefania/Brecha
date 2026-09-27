#!/usr/bin/env python3
"""
Step 9 - district-level ASKING rent (Idealista, via the Ayuntamiento's Banco de Datos).

Runs before step 10 (JSON export), which reads this step's output - despite steps 1-8
having been written first, this one was added later and had to be numbered to match
where it actually belongs in the run order, not when it was written.

Why this exists: the site's main rent series (SERPAVI, step 3) is the rent of contracts
already IN FORCE, declared to the tax office - it lags and understates what a new tenant is
asked today. This series is the independent counterpart: the price
asked in NEW listings, monthly, by district, 2008-2024. District level only - there is no
barrio-level equivalent we can legally/reliably use.

Source: Ayuntamiento de Madrid, Banco de Datos, series 0504030000213 ("Evolucion del precio de
oferta de alquiler de la vivienda (EUR/m2) por Distrito y Mes"), fetched with the same
session/cookie export flow as the purchase-price series (see 05_purchase.py's docstring;
variables Ano / Distrito / Mes) and saved locally to
data/raw/banco_datos_alquiler_oferta_distrito_2008_2024.csv. The underlying data is Idealista's
(third party); its reuse terms for this specific series haven't been confirmed as open, so it
isn't redistributed - only this script, which anyone can run against their own copy of the file.

Cleaning (audit finding): the source contains obvious typos - Ciudad Lineal May 2023 = 149.0
(evidently 14.9), Usera Oct 2019 = 21.1 against neighbours of ~11.8. Rule: a month that is more
than OUTLIER_TOLERANCE (30%) away from the median of its six neighbouring months (3 before, 3
after) is dropped, then the year is the mean of the remaining months, published only if at
least MIN_MONTHS months remain. Dropped months are counted in the output, never silently lost.

Usage:
    python pipeline/09_rent_asking.py build

Output: data/processed/rent_asking_by_district.csv
    district_code, district_name, year, rent_asking_m2, n_months, n_outliers_dropped
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW_PATH = ROOT / "data" / "raw" / "banco_datos_alquiler_oferta_distrito_2008_2024.csv"
OUT = ROOT / "data" / "processed"

OUTLIER_TOLERANCE = 0.30
MIN_MONTHS = 6

DISTRICT_NAMES = {
    "01": "Centro", "02": "Arganzuela", "03": "Retiro", "04": "Salamanca",
    "05": "Chamartín", "06": "Tetuán", "07": "Chamberí", "08": "Fuencarral-El Pardo",
    "09": "Moncloa-Aravaca", "10": "Latina", "11": "Carabanchel", "12": "Usera",
    "13": "Puente de Vallecas", "14": "Moratalaz", "15": "Ciudad Lineal", "16": "Hortaleza",
    "17": "Villaverde", "18": "Villa de Vallecas", "19": "Vicálvaro",
    "20": "San Blas-Canillejas", "21": "Barajas",
}


def parse_monthly(path: Path) -> pd.DataFrame:
    """Rows = (year, month) in file order, columns = district code, values = EUR/m2."""
    if not path.exists():
        sys.exit(f"{path} not found (manually-fetched raw source, should be in the repo).")
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    year_row = next(l for l in lines if l.startswith(";2008"))
    years = [int(x) for x in year_row.split(";")[1:]]
    n = len(years)
    months = [(i % 12) + 1 for i in range(n)]
    data: dict[str, list[float]] = {}
    for line in lines:
        m = re.match(r"^(\d\d)\. [^;]+;(.*)$", line)
        if not m:
            continue
        cells = next(csv.reader([m.group(2)], delimiter=";", quotechar='"'))
        if len(cells) != n:
            sys.exit(f"district {m.group(1)} has {len(cells)} monthly cells, expected {n}")
        data[m.group(1)] = [
            np.nan if c.strip() in ("", "..", "-", "0") else float(c.replace(".", "").replace(",", "."))
            for c in cells
        ]
    if len(data) != 21:
        sys.exit(f"expected 21 districts, parsed {len(data)}")
    index = pd.MultiIndex.from_arrays([years, months], names=["year", "month"])
    return pd.DataFrame(data, index=index)


def drop_outlier_months(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Returns (cleaned series, boolean 'was dropped' series), same index."""
    values = series.reset_index(drop=True)
    dropped = pd.Series(False, index=values.index)
    for i in range(len(values)):
        v = values.iloc[i]
        if pd.isna(v):
            continue
        neighbours = pd.concat([values.iloc[max(0, i - 3):i], values.iloc[i + 1:i + 4]]).dropna()
        if len(neighbours) >= 3:
            ref = neighbours.median()
            if abs(v / ref - 1) > OUTLIER_TOLERANCE:
                dropped.iloc[i] = True
    cleaned = values.mask(dropped)
    cleaned.index = series.index
    dropped.index = series.index
    return cleaned, dropped


def cmd_build(args: argparse.Namespace) -> None:
    monthly = parse_monthly(RAW_PATH)
    rows = []
    total_dropped = []
    for code in monthly.columns:
        cleaned, dropped = drop_outlier_months(monthly[code])
        for month_index in cleaned.index[dropped.values]:
            total_dropped.append((code, month_index, float(monthly[code].loc[month_index])))
        for year, g in cleaned.groupby(level="year"):
            valid = g.dropna()
            rows.append({
                "district_code": code,
                "district_name": DISTRICT_NAMES[code],
                "year": int(year),
                "rent_asking_m2": float(valid.mean()) if len(valid) >= MIN_MONTHS else np.nan,
                "n_months": int(len(valid)),
                "n_outliers_dropped": int(dropped.loc[g.index].sum()),
            })
    out = pd.DataFrame(rows).sort_values(["district_code", "year"])
    OUT.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT / "rent_asking_by_district.csv", index=False, encoding="utf-8")
    print(f"Wrote {OUT / 'rent_asking_by_district.csv'} ({len(out)} rows, "
          f"{out['district_code'].nunique()} districts, years {out['year'].min()}-{out['year'].max()})")
    print(f"outlier months dropped ({len(total_dropped)}):")
    for code, (year, month), value in total_dropped:
        print(f"  district {code} {year}-{month:02d}: {value}")
    thin = out[out["rent_asking_m2"].isna()]
    print(f"district-years without a published value (fewer than {MIN_MONTHS} valid months): {len(thin)}")
    if len(thin):
        print(thin[["district_code", "year", "n_months"]].to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build").set_defaults(fn=cmd_build)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
