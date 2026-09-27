#!/usr/bin/env python3
"""
Step 6 - Postal code -> barrio crosswalk.

Downloads the Ayuntamiento's address directory ("Callejero. Informacion
adicional asociada", dataset 200075, ~200,000 numbered addresses with
district/barrio/census-section/postal-code already attached to each one) and
counts, for every postal code, how many addresses fall in each barrio. A
postal code is not a subset of one barrio - many straddle two or more - so
this is a many-to-many crosswalk with a share per pair, not a lookup table.

Used for the postal-code SEARCH BOX only (decision: jump to the barrio with
the most addresses under that postal code; never draw a map by postal code,
no official open boundaries for that exist).

Usage (run from the project folder):
    python pipeline/06_postal_crosswalk.py inspect   # download + preview columns
    python pipeline/06_postal_crosswalk.py build     # build the crosswalk, write CSV

Output (data/processed/):
    postal_code_to_barrio.csv   postal_code, barrio_code, barrio_name,
                                 address_count, share (of that postal code's
                                 addresses), rank (1 = the barrio the search
                                 box should jump to for that postal code)
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

CALLEJERO_URL = (
    "https://datos.madrid.es/dataset/200075-0-callejero/resource/"
    "200075-1-callejero-csv/download/200075-1-callejero-csv.csv"
)
HEADERS = {"User-Agent": "Mozilla/5.0 (brecha-madrid data pipeline)"}
COLS = ["Codigo postal", "Codigo de distrito", "Codigo de barrio", "Nombre del barrio"]


def download(force: bool = False) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    dest = RAW / "callejero.csv"
    if dest.exists() and not force:
        print(f"  already downloaded ({dest.name})")
        return dest
    print(f"  downloading {CALLEJERO_URL}")
    try:
        req = urllib.request.Request(CALLEJERO_URL, headers=HEADERS)
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
            f"\nCould not download the address directory: {exc}\n"
            f"Download it manually in a browser from:\n  {CALLEJERO_URL}\n"
            f"and save it as:\n  {dest}\nthen run the command again."
        )
    return dest


def load_raw(force: bool = False) -> pd.DataFrame:
    path = download(force)
    return pd.read_csv(path, sep=";", encoding="latin1", usecols=COLS, dtype=str)


def cmd_inspect(args: argparse.Namespace) -> None:
    print("Downloading / loading the address directory...")
    df = load_raw(args.force)
    print(f"\naddress rows: {len(df)}")
    print(f"distinct postal codes: {df['Codigo postal'].nunique()}")
    print(df.head(6).to_string(index=False))


def cmd_build(args: argparse.Namespace) -> None:
    print("Downloading / loading the address directory...")
    df = load_raw(args.force)
    df = df.dropna(subset=["Codigo postal", "Codigo de distrito", "Codigo de barrio"])
    # "Codigo de barrio" is zero-padded to 2 digits (e.g. "05"); the barrio_code scheme used
    # elsewhere in this pipeline (section_to_barrio.csv etc.) is district(2) + barrio number
    # UNPADDED (e.g. "205", not "2005") - strip the padding before concatenating.
    df["barrio_code"] = df["Codigo de distrito"].str.zfill(2) + df["Codigo de barrio"].astype(int).astype(str)

    counts = (df.groupby(["Codigo postal", "barrio_code", "Nombre del barrio"])
              .size().reset_index(name="address_count")
              .rename(columns={"Codigo postal": "postal_code", "Nombre del barrio": "barrio_name"}))
    counts["share"] = counts["address_count"] / counts.groupby("postal_code")["address_count"].transform("sum")
    counts = counts.sort_values(["postal_code", "address_count"], ascending=[True, False])
    counts["rank"] = counts.groupby("postal_code").cumcount() + 1

    OUT.mkdir(parents=True, exist_ok=True)
    counts = counts[["postal_code", "barrio_code", "barrio_name", "address_count", "share", "rank"]]
    counts.to_csv(OUT / "postal_code_to_barrio.csv", index=False, encoding="utf-8")
    print(f"\nWrote {OUT / 'postal_code_to_barrio.csv'} ({len(counts)} rows)")

    n_postal = counts["postal_code"].nunique()
    multi = counts[counts["rank"] == 2]["postal_code"].nunique()
    print(f"distinct postal codes: {n_postal}")
    print(f"postal codes spanning >1 barrio: {multi} ({multi / n_postal:.0%})")

    ambiguous = counts[(counts["rank"] == 1) & (counts["share"] < 0.6)]
    print(f"postal codes where the top barrio has <60% of addresses (weak primary match): {len(ambiguous)}")
    print(ambiguous.sort_values("share").head(8)[["postal_code", "barrio_name", "share"]].to_string(index=False))

    crosswalk_path = OUT / "section_to_barrio.csv"
    if crosswalk_path.exists():
        known_barrios = set(pd.read_csv(crosswalk_path, dtype=str)["barrio_code"])
        unknown = sorted(set(counts["barrio_code"]) - known_barrios)
        if unknown:
            print(f"\nWARNING: barrio codes in the address directory not seen in section_to_barrio.csv: {unknown}")
        else:
            print(f"\ncross-check vs section_to_barrio.csv: all {counts['barrio_code'].nunique()} barrio codes recognized")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, fn in (("inspect", cmd_inspect), ("build", cmd_build)):
        p = sub.add_parser(name)
        p.add_argument("--force", action="store_true")
        p.set_defaults(fn=fn)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
