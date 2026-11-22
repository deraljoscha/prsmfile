# prsmfile

Read the results and data tables stored in GraphPad Prism `.prism` files, without Prism.
Pure Python, standard library only, works on any OS with Python 3.10 or newer.

prsmfile reads files created by GraphPad Prism. It is an independent project and is not affiliated with, endorsed or sponsored by Dotmatics or GraphPad Software. GraphPad Prism is a trademark of its respective owner.

A `.prism` file is a zip archive of JSON and CSV members. When Prism has calculated an
analysis, the numbers are stored in the file. prsmfile turns them into plain tables, JSON or
CSV so you can check, reuse or archive results without opening Prism. The format is not
documented by the vendor; `docs/format.md` records what was observed in 75 public files.

## Install

```
pip install git+https://github.com/deraljoscha/prsmfile
```

This will become `pip install prsmfile` once the package is published.

## Command line

```
prsmfile FILE [--list] [--json] [--csv DIR] [--data] [--analysis TEXT]
```

List the analyses and whether results are stored:

```
$ prsmfile examples/cc0-figure4.prism --list
01  NORMALITY_TESTS  calculated  Normality and Lognormality Tests of Frequency
02  T_TESTS_AND_NONPARAMETRIC  calculated  Mann-Whitney test of Frequency
...
05  NORMALITY_TESTS  calculated  Normality and Lognormality Tests of WT Baseline
06  T_TESTS_AND_NONPARAMETRIC  calculated  Welch's t test of WT Baseline
...
10  T_TESTS_AND_NONPARAMETRIC  no stored results  Kolmogorov-Smirnov test
...
```

Show one analysis as text tables (`--analysis` matches a case-insensitive part of the title):

```
$ prsmfile examples/cc0-figure4.prism --analysis "Welch's t test of WT"
File: examples/cc0-figure4.prism
created with Prism 10.0.0.153, saved with Prism 10.0.0.153, format 1-0-0

== 01 Welch's t test of WT Baseline [T_TESTS_AND_NONPARAMETRIC] ==

Parameters
Name            Value
--------------  ------------
Design          WELCH_T_TEST
Tails           two
Swap direction  yes

Test
Test                         Statistic  Value    df      P
---------------------------  ---------  -------  ------  --------
Welch's t test               t          4.81936  8.7456  0.001028
F test to compare variances  F          1.01646  5, 16   0.8805
...
```

Other outputs:

```
prsmfile FILE --json                # everything as one JSON document
prsmfile FILE --json --data         # plus the raw data tables
prsmfile FILE --csv out_dir         # one CSV per section, plus index.csv
```

`--csv` writes into a new or empty directory. It builds the files in a temporary directory
next to the target and renames it at the end, so a failed export leaves nothing behind and an
existing non-empty directory is never touched. Exit status is 1 for unreadable files and other
errors, 2 for wrong command line options.

## Python

```python
import prsmfile

with prsmfile.open("examples/cc0-figure4.prism") as pf:
    for a in pf.analyses():
        print(prsmfile.read_analysis(pf, a).to_dict())
```

`read_analysis` returns a `Report` with a `kind` (`structured`, `generic` or `not_calculated`),
a list of `Section`s (title, columns, rows, optional note) and warnings.

## Supported analyses

Structured readers (named columns, p-values with their bounds and significance) exist for five
analysis families:

- t tests and nonparametric two-sample tests (Welch, unpaired, paired, Mann-Whitney, Wilcoxon)
- one-way ANOVA (ordinary and repeated measures)
- two-way ANOVA (ordinary, repeated measures GLM, mixed model REML)
- nonlinear regression
- area under curve

Every other analysis class, and every analysis whose stored layout a structured reader cannot
handle, goes through a generic reader that lists all stored values as `path, value` rows, so
nothing is dropped silently.

## Known limitations

- Only analyses with stored results can be read. If Prism saved an analysis without results
  (not calculated), prsmfile says so. Open the file in Prism, view the results and save again.
- Files written by Prism 10.0 often carry result stubs. For those, the rendered result tables
  are shown instead, marked as rounded values.
- In repeated measures GLM two-way ANOVA the subjects row is only present in Prism's rendered
  table, not in the stored numbers. prsmfile prints a warning in that case.
- Text tables align by character count. Wide characters (for example CJK) occupy two columns in a
  terminal, so such columns look misaligned. JSON and CSV output are not affected.
- `.pzf` files (Prism's other file format) are not supported. Save the project as `.prism`.
- Graphs, layouts and embedded media are not read.
- Only the five structured families above get dedicated readers; other analyses are generic.
- For unpaired tests, the stored `swapDirection` flag is not trusted. The direction of a
  difference is derived from the stored means.

## Tests and the corpus

```
pip install -e '.[test]'
pytest -q
```

The default run uses synthetic files built by `tests/builder.py`. A larger check runs against 75
public CC0 and CC-BY files from Zenodo. They are not part of this repository. Fetch them (the
script verifies SHA256 hashes) and run the corpus tests:

```
python scripts/fetch_corpus.py
pytest -q tests/test_corpus.py -s
```

Without a `corpus/` directory the corpus tests are skipped.

## Contributing

To add a reader for another analysis class, see `docs/readers.md`. The file format notes are in
`docs/format.md`. Please attach only files you may share, and never real personal data.

## License

MIT, see `LICENSE`.
