# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Breaking changes in 0.x releases are listed here.

## [Unreleased]

## [0.1.0] - 2026-11-22

### Added

- Readers for `.prism` files (zip archives of JSON and CSV members) that extract stored analysis results and raw data tables without Prism.
- Structured readers for t tests and nonparametric two-sample tests, one-way ANOVA, two-way ANOVA, nonlinear regression and area under curve.
- Generic fallback reader that lists all stored values as `path, value` rows for every other analysis class, so nothing is dropped silently.
- Command line tool `prsmfile` with `--list`, `--analysis`, `--data`, `--json` and `--csv DIR`.
- JSON output with the report sections, and CSV export with one file per section plus `index.csv`.
- Python API: `prsmfile.open`, `read_analysis`, `read_table` and a reader registry.
- Warnings for result stubs, not calculated analyses and other known limitations.

[Unreleased]: https://github.com/deraljoscha/prsmfile/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/deraljoscha/prsmfile/releases/tag/v0.1.0
