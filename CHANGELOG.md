# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Breaking changes in 0.x releases are listed here.

## [Unreleased]

### Security

- Archive reading is bounded against zip bombs and oversized members: at most 100,000 members, a member list of 64 MiB, 512 MiB per member read, 4 GiB in total per opened file (each member counted once, bytes of failed reads included, counter protected by a lock), and a compression ratio of at most 200 for members above 10 MiB. Member count and member list size are checked from the end-of-central-directory records (also zip64) before the list is parsed. Members are read through a bounded reader and must be exactly as long as their header says, so a false size in the archive header can neither bypass the limits nor truncate data silently. Only stored and deflate members are read; bzip2 and lzma members are rejected because their decompression is not bounded. A violation raises `PrismFormatError` naming the member and the limit (CLI exit 1).

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
