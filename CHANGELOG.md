# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Breaking changes in 0.x releases are listed here.

## [Unreleased]

### Changed

- Repeated measures two-way ANOVA with mixed model REML: column names change in the affected cases, which matters for JSON and CSV consumers. When sphericity is not assumed, DFn, DFd and P of the Fixed effects section become "DFn (uncorrected)", "DFd (uncorrected)" and "P (uncorrected)". With REML and the post test design "compare cells by rows within columns, separate families", the multiple comparisons columns Mean diff, SE, CI lower, CI upper, Statistic, P adjusted and P individual get the same suffix. When a REML model has a subject variance of exactly 0, DFd and P of Fixed effects are marked. Values are unchanged. GLM models get no column marks.

### Fixed

- The blanket warning for all repeated measures two-way ANOVA is replaced by precise warnings (REML: sphericity not assumed, subject variance 0; GLM: sphericity not assumed, stored values are Geisser-Greenhouse corrected) that name the reason and the affected sections. Analyses with sphericity assumed and a subject variance above 0 match Prism and carry no warning.

## [0.1.1] - 2026-11-23

### Security

- Archive reading is bounded against zip bombs and oversized members: the file may be at most 2 GiB (checked before the member list is parsed; file objects must be seekable), with at most 100,000 members, 512 MiB per member and 4 GiB read in total per opened file (each member counted once, bytes of failed reads included, counter protected by a lock). The file is opened once and the size checked on that handle. Sizes in the archive are not trusted: members are counted as they are read through a bounded reader. Only stored and deflate members are read; bzip2 and lzma members are rejected because their decompression is not bounded. Archives with duplicate member names are rejected. A violation raises `PrismFormatError` naming the limit, and the member for the per-member and total limits (CLI exit 1). Corrupt members are handled as before.

### Known issues

- Repeated measures two-way ANOVA (GLM and mixed model REML): a cross-check against Prism exports found differences in some degrees of freedom, P values, confidence limits and multiple comparisons. These analyses now carry a warning. A fix is planned for 0.1.2.

## [0.1.0] - 2026-11-22

### Added

- Readers for `.prism` files (zip archives of JSON and CSV members) that extract stored analysis results and raw data tables without Prism.
- Structured readers for t tests and nonparametric two-sample tests, one-way ANOVA, two-way ANOVA, nonlinear regression and area under curve.
- Generic fallback reader that lists all stored values as `path, value` rows for every other analysis class, so nothing is dropped silently.
- Command line tool `prsmfile` with `--list`, `--analysis`, `--data`, `--json` and `--csv DIR`.
- JSON output with the report sections, and CSV export with one file per section plus `index.csv`.
- Python API: `prsmfile.open`, `read_analysis`, `read_table` and a reader registry.
- Warnings for result stubs, not calculated analyses and other known limitations.

[Unreleased]: https://github.com/deraljoscha/prsmfile/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/deraljoscha/prsmfile/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/deraljoscha/prsmfile/releases/tag/v0.1.0
