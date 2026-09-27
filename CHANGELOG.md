# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and version numbers
follow [Semantic Versioning](https://semver.org/): MAJOR for a breaking change
to the pipeline's output schema or the site's data contract, MINOR for a new
feature (a new layer, a new data source), PATCH for a fix that doesn't change
either.

## [Unreleased]

## [0.1.0] - 2026-09-27

### Added

- Data pipeline (`pipeline/01`-`10`): boundaries, income, rent, household-
  weighted barrio/district aggregation, purchase price (barrio and district,
  total/new-build/second-hand), postal-code crosswalk, year-overlap check,
  JSON export for the site, and district-level asking rent.
- Static site (`site/`): bivariate and single-variable map layers (Esfuerzo,
  Cruce, Renta, Alquiler, Compra), a Hogar/Persona income toggle, Contratos-
  en-vigor/Precio-de-oferta and Total/Obra-nueva/Segunda-mano price-source
  switches, a year slider (2015-2025, with projected years past each source's
  real data flagged), a "compare with 2015" mode, rent/buy effort calculators,
  an index chart, postal-code search, and a methodology page.

### Notes

- This version ships no data (see "About the data" in `README.md`).
