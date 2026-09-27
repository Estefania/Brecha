#!/usr/bin/env python3
"""
Step 10 - JSON export for the site.

Packages every data/processed/*.csv from steps 2-9 into the JSON files the
static site (site/) fetches directly, plus copies the two boundary GeoJSON
files from step 1. Output goes to data/site/, kept separate from
data/processed/ (pipeline-internal CSVs) so the site only ever reads from one
folder. Runs last on purpose - it depends on every other step's output,
including step 9's.

Usage (run from the project folder):
    python pipeline/10_export_json.py build

Output (data/site/):
    meta.json           years covered at each level, generated_at, sources
    barrios.json         one record per barrio: identity + income (2015-2023),
                          rent (2015-2024) and purchase price (2015-2025, all
                          three types) time series
    districts.json        one record per district: identity + a combined
                          income/rent/purchase/asking-rent time series
                          (DISTRICT_EXPORT_FROM.. ; purchase itself goes back
                          to 2007 in the processed CSV, see step 5) - this is
                          what the year slider reads
    postal_codes.json     postal_code -> ranked list of candidate barrios,
                          for the search box (see step 6's finding: many
                          postal codes are a weak match to any one barrio -
                          the UI needs to use this ranked list, not just rank 1)
    distritos.geojson, barrios.geojson   copied unchanged from step 1
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"
SITE = ROOT / "data" / "site"

DISTRICT_EXPORT_FROM = 2015

INCOME_COLS = ["net_income_person", "net_income_household", "gross_income_person",
               "gross_income_household", "mean_income_cu", "median_income_cu"]


def r(x, ndigits=0):
    if pd.isna(x):
        return None
    v = round(float(x), ndigits)
    return int(v) if ndigits == 0 else v


def build_barrios() -> list[dict]:
    income = pd.read_csv(PROCESSED / "income_by_barrio.csv", dtype={"barrio_code": str})
    rent = pd.read_csv(PROCESSED / "rent_by_barrio.csv", dtype={"barrio_code": str})
    purchase = pd.read_csv(PROCESSED / "purchase_price_by_barrio.csv", dtype={"barrio_code": str})

    names = income[["barrio_code", "barrio_name"]].drop_duplicates().set_index("barrio_code")["barrio_name"]
    codes = sorted(set(income["barrio_code"]) | set(rent["barrio_code"]) | set(purchase["barrio_code"]))

    out = []
    for code in codes:
        income_series = {}
        for _, row in income[income["barrio_code"] == code].iterrows():
            income_series[str(int(row["year"]))] = {
                **{c: r(row[c]) for c in INCOME_COLS},
                "household_coverage": r(row["household_coverage"], 3),
            }
        rent_series = {}
        for _, row in rent[rent["barrio_code"] == code].iterrows():
            rent_series[str(int(row["year"]))] = {
                "rent_m2": r(row["rent_m2"], 2),
                "household_coverage": r(row["household_coverage"], 3),
            }
        purchase_rows = purchase[purchase["barrio_code"] == code]
        purchase_series = {}
        for _, row in purchase_rows.iterrows():
            purchase_series[str(int(row["year"]))] = {
                "price_m2_total": r(row["price_m2_total"]),
                "price_m2_new": r(row["price_m2_new"]),
                "price_m2_used": r(row["price_m2_used"]),
            }
        out.append({
            "barrio_code": code,
            "barrio_name": names.get(code, purchase_rows["barrio_name"].iloc[0] if len(purchase_rows) else code),
            "district_code": code[:2],
            "income": income_series,
            "rent": rent_series,
            "purchase": purchase_series,
        })
    return out


def build_districts() -> list[dict]:
    income = pd.read_csv(PROCESSED / "income_by_district.csv", dtype={"district_code": str})
    rent = pd.read_csv(PROCESSED / "rent_by_district.csv", dtype={"district_code": str})
    purchase = pd.read_csv(PROCESSED / "purchase_price_by_district.csv", dtype={"district_code": str})
    # The processed CSV holds the OFFICIAL district series back to 2007 (see
    # pipeline/05_purchase.py), but income only starts in 2015 and every effort comparison
    # needs it, so the site export starts at DISTRICT_EXPORT_FROM. Lower it (and decide how
    # the index chart should handle lines that start years before income) to expose more.
    purchase = purchase[purchase["year"] >= DISTRICT_EXPORT_FROM]
    purchase_wide = purchase.pivot_table(index=["district_code", "year"], columns="type",
                                          values="price_m2", aggfunc="first").reset_index()

    # District-only ASKING rent (Idealista via the Ayuntamiento, pipeline/09_rent_asking.py): the
    # price of new listings, next to SERPAVI's rent of contracts in force. Blank where that step
    # published no value. Optional on purpose (an empty frame if step 9 hasn't been run at all) so
    # this export still produces valid JSON without it, just missing rent_asking_m2.
    asking_path = PROCESSED / "rent_asking_by_district.csv"
    if asking_path.exists():
        asking = pd.read_csv(asking_path, dtype={"district_code": str})
        asking = asking[(asking["year"] >= DISTRICT_EXPORT_FROM) & asking["rent_asking_m2"].notna()]
    else:
        print(f"WARNING: {asking_path} not found, run 'python pipeline/09_rent_asking.py build' "
              f"(then this step again) to include asking rent.")
        asking = pd.DataFrame(columns=["district_code", "year", "rent_asking_m2"])

    names = income[["district_code", "district_name"]].drop_duplicates().set_index("district_code")["district_name"]
    out = []
    for code in sorted(names.index):
        series = {}
        inc = income[income["district_code"] == code].set_index("year")
        rnt = rent[rent["district_code"] == code].set_index("year")
        pur = purchase_wide[purchase_wide["district_code"] == code].set_index("year")
        ask = asking[asking["district_code"] == code].set_index("year")
        years = sorted(set(inc.index) | set(rnt.index) | set(pur.index) | set(ask.index))
        for year in years:
            entry = {}
            if year in inc.index:
                row = inc.loc[year]
                entry["net_income_household"] = r(row["net_income_household"])
                entry["net_income_person"] = r(row["net_income_person"])
                entry["income_household_coverage"] = r(row["household_coverage"], 3)
            if year in rnt.index:
                row = rnt.loc[year]
                entry["rent_m2"] = r(row["rent_m2"], 2)
                entry["rent_household_coverage"] = r(row["household_coverage"], 3)
            if year in ask.index:
                entry["rent_asking_m2"] = r(ask.loc[year, "rent_asking_m2"], 2)
            if year in pur.index:
                row = pur.loc[year]
                entry["price_m2_new"] = r(row.get("new")) if "new" in pur.columns else None
                entry["price_m2_used"] = r(row.get("used")) if "used" in pur.columns else None
                entry["price_m2_total"] = r(row.get("total")) if "total" in pur.columns else None
            series[str(int(year))] = entry
        out.append({"district_code": code, "district_name": names[code], "timeseries": series})
    return out


def build_postal_codes() -> dict:
    df = pd.read_csv(PROCESSED / "postal_code_to_barrio.csv", dtype={"postal_code": str, "barrio_code": str})
    out: dict[str, list[dict]] = {}
    for postal_code, g in df.groupby("postal_code"):
        out[postal_code] = [
            {"barrio_code": row["barrio_code"], "barrio_name": row["barrio_name"], "share": r(row["share"], 3)}
            for _, row in g.sort_values("rank").iterrows()
        ]
    return out


def cmd_build(args: argparse.Namespace) -> None:
    SITE.mkdir(parents=True, exist_ok=True)

    barrios = build_barrios()
    (SITE / "barrios.json").write_text(json.dumps(barrios, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {SITE / 'barrios.json'} ({len(barrios)} barrios)")

    districts = build_districts()
    (SITE / "districts.json").write_text(json.dumps(districts, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {SITE / 'districts.json'} ({len(districts)} districts)")

    postal_codes = build_postal_codes()
    (SITE / "postal_codes.json").write_text(json.dumps(postal_codes, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {SITE / 'postal_codes.json'} ({len(postal_codes)} postal codes)")

    for name in ("distritos.geojson", "barrios.geojson"):
        src = PROCESSED / name
        if src.exists():
            shutil.copyfile(src, SITE / name)
            print(f"Copied {SITE / name}")
        else:
            print(f"WARNING: {src} not found, run 'python pipeline/01_boundaries.py check --export-geojson' first")

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "years_barrio_income": sorted({int(y) for b in barrios for y in b["income"]}),
        "years_barrio_rent": sorted({int(y) for b in barrios for y in b["rent"]}),
        "years_barrio_purchase": sorted({int(y) for b in barrios for y in b["purchase"]}),
        "years_district_income_rent": sorted({int(y) for d in districts for y in d["timeseries"]}),
        # Requires ALL THREE metrics present in the SAME year's entry, not just purchase
        # price presence - purchase price alone no longer implies income+rent are also
        # present now that it extends past both of them (barrio-rollup fills 2023-2025,
        # see pipeline/05_purchase.py), so checking purchase price alone would wrongly
        # include years like 2024/2025 that have no income data at all.
        "years_district_all_three_metrics": sorted({
            int(y) for d in districts for y, entry in d["timeseries"].items()
            if entry.get("net_income_household") is not None and entry.get("rent_m2") is not None
            and any(entry.get(k) is not None for k in ("price_m2_new", "price_m2_used", "price_m2_total"))
        }),
        "sources": {
            "income": "INE, Atlas de Distribucion de Renta de los Hogares",
            "rent": "MIVAU, SERPAVI (tax-based, IRPF Modelo 100; rent of contracts in force)",
            "rent_asking": "Idealista asking rents (new listings), district level, via Ayuntamiento de Madrid Banco de Datos",
            "purchase_price": "Ayuntamiento de Madrid, Estadistica Registral Inmobiliaria "
                               "(Colegio de Registradores; official district and barrio figures)",
            "households": "Ayuntamiento de Madrid, Padron Municipal (Hogares por tamano...)",
            "boundaries": "Madrid Geoportal, Limites administrativos actuales",
        },
    }
    (SITE / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {SITE / 'meta.json'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("build")
    p.set_defaults(fn=cmd_build)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
