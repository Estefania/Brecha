# Brecha Madrid

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.1.0-lightgrey.svg)](#)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](#what-you-need)
[![Data: not bundled](https://img.shields.io/badge/data-not_bundled-orange.svg)](#about-the-data)

The license badge covers the **code** only; the data badge links to why the
data itself isn't bundled.

## Versioning

The version number lives in `VERSION` (currently the only source of truth -
the README badge above is a static image, bump it by hand alongside
`VERSION` and `CHANGELOG.md`). It follows [Semantic Versioning](https://semver.org/):
MAJOR for a breaking change to the pipeline's output schema or the site's
data contract, MINOR for a new feature, PATCH for a fix that changes neither.
See `CHANGELOG.md` for what changed in each version. There's no git tag or
GitHub release behind it yet - `git tag v$(cat VERSION)` after committing is
the natural next step once this is pushed somewhere.

A free, static website comparing net income against rent and purchase price per
m² by district and barrio (neighbourhood) in the city of Madrid.

A Python pipeline downloads and processes public data into `data/site/*.json`;
a plain HTML/CSS/JS site (no build step, no framework) reads that JSON to
render the map and panels.

**This repo ships code only, no data** (see "About the data" below) - you
build your own copy of `data/` by running the pipeline.

## What you need

- Python 3.10 or newer (`python3 --version`)
- An internet connection (the pipeline downloads roughly 200 MB in total,
  mostly re-downloadable source files - see `.gitignore`)
- Roughly 1 GB of free disk space
- Nothing else: no accounts, no API keys, no Node.js

## Setup (once)

```bash
git clone <this-repo>
cd brecha-madrid
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

`pip install geopandas` failing on Windows is common; install it with conda
instead (`conda install -c conda-forge geopandas`) if that happens.

## Running the pipeline

The pipeline is a sequence of numbered scripts in `pipeline/`, each with an
`inspect` (preview, no side effects beyond downloading) and/or `build`/`check`
command. Run them in order from the project root:

```bash
python pipeline/01_boundaries.py check --export-geojson
python pipeline/02_income.py build
python pipeline/03_rent.py build
python pipeline/04_barrio_aggregate.py build
python pipeline/05_purchase.py build
python pipeline/06_postal_crosswalk.py build
python pipeline/07_year_overlap.py check
python pipeline/08_district_aggregate.py build
python pipeline/09_rent_asking.py build
python pipeline/10_export_json.py build
```

Each script's own docstring (`python pipeline/NN_*.py --help`, or just open the
file) explains what it does, what it reads, and what it writes to
`data/processed/`. Step 10 is the one that actually produces the JSON the site
reads, in `data/site/` - re-run it after re-running any earlier step.

Steps 05 and 09 do not download anything themselves - they read raw files
under `data/raw/` that you have to fetch by hand first (`banco_datos_*.csv`).
Their docstrings give the exact reverse-engineered fetch sequence (which URLs,
in what order, against the same session) to get them; this isn't automated
because the flow is fragile and the source doesn't offer a normal download
link, not because of anything license-related - see "About the data" for the
separate reason the results aren't checked into the repo.

If any other step's download fails, the error message gives you the URL: open
it in a browser, save the file under the name shown in `data/raw/`, and run
the command again.

## About the data

None of `data/` is committed to this repo (see `.gitignore`) - not the raw
downloads, not the intermediate CSVs, not even the final `data/site/*.json`
the site reads. This is deliberate, not an oversight: purchase prices
(Colegio de Registradores) and asking rent (Idealista) are both republished
by the Ayuntamiento de Madrid, but neither party's own terms clearly permit
redistributing that data further, even in a derived/aggregated form - see the
relevant pipeline scripts' own docstrings (`pipeline/05_purchase.py`,
`pipeline/09_rent_asking.py`) for the specifics. The code to fetch and
process it is free to reuse (MIT); the data itself, you build yourself by
running the pipeline, under your own use of each source.

## Running the site

The site is plain HTML/CSS/JS with no build step - any static file server
works:

```bash
python -m http.server 8123
```

then open `http://localhost:8123/site/index.html`. Run the full pipeline
first (`data/site/*.json` must exist) - the site does not run the pipeline
itself.

## Project layout

- `pipeline/` - the data pipeline, steps 01-10, run in order
- `data/raw/`, `data/processed/`, `data/site/` - not committed (see "About the
  data"); the pipeline creates and fills these
- `site/` - the static site itself (`index.html`, `css/`, `js/`)
- `LICENSE` - MIT, covers the code only, not the data (see "About the data")
