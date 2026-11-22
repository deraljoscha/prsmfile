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
pip install prsmfile
```

To install the development version from GitHub instead:

```
pip install git+https://github.com/deraljoscha/prsmfile
```

## Stability

The `.prism` format is undocumented and reverse engineered. The Python API, the CLI output and
the JSON and CSV layout may change in 0.x releases. Breaking changes are listed in `CHANGELOG.md`.

## Command line

```
prsmfile FILE [--list] [--json] [--csv DIR] [--data] [--analysis TEXT]
```

List the analyses and whether results are stored. The numbers are stable: every output uses
the number shown here, also when `--analysis` selects a subset.

```
$ prsmfile examples/example.prism --list
01  T_TESTS_AND_NONPARAMETRIC  calculated  Welch's t test of Lysozyme activity
02  ONE_WAY_ANOVA  calculated  Ordinary one-way ANOVA of Shoot dry mass
03  NORMALITY_TESTS  calculated  Normality and Lognormality Tests of Shoot dry mass
04  TWO_WAY_ANOVA  calculated  Ordinary two-way ANOVA of Root length
05  AREA_UNDER_CURVE  calculated  Area under the curve of Tracer clearance
```

Show one analysis as text tables. `--analysis` takes the number from `--list` (`02`, ASCII digits only), an
analysis id, or else a case-insensitive part of the title. A pure number that matches no analysis is an
error (`no analysis numbered N`) and never searches titles:

```
$ prsmfile examples/example.prism --analysis 02
File: examples/example.prism
created with Prism 11.1.0.224, saved with Prism 11.1.0.224, format 1-6-1

== 02 Ordinary one-way ANOVA of Shoot dry mass [ONE_WAY_ANOVA] ==

Parameters
Name                    Value
----------------------  --------------
Design                  ORDINARY_ANOVA
Post test design        ALL_VS_ALL
Method                  Tukey
Comparisons per family  3

ANOVA
Source     SS       df  MS       F        DFn  DFd  P          R squared
---------  -------  --  -------  -------  ---  ---  ---------  ---------
Treatment  5364.56  2   2682.28  37.1094  2    15   1.557e-06  0.831874
Residual   1084.21  15  72.2803
Total      6448.77  17
...
```

`examples/example.prism` is a synthetic file with invented data, see `examples/README.md`.

Other outputs:

```
prsmfile FILE --json                # the report sections as one JSON document (each analysis
                                    # carries its list number as "number")
prsmfile FILE --json --data         # plus the raw data tables
prsmfile FILE --csv out_dir         # one CSV per section, plus index.csv
```

`--json` holds what the readers extract, not every stored number: for example the covariances
of a nonlinear regression are not in it. Use `Analysis.results` from Python for the complete
stored values. Text and CSV show the p-value number (with a `>` for a bound), JSON also carries
the stored significance verdict and alpha of each p-value. Text and CSV write booleans as
`yes` and `no`, JSON as `true` and `false`.

`--csv` writes into a new or empty directory. It builds the files in a temporary directory
next to the target and renames it at the end, so a failed export leaves nothing behind (also
no parent directories it created) and an existing non-empty directory is never touched. Exit
status is 1 for unreadable files and other errors, 2 for wrong command line options
(`--list` cannot be combined with `--data`).

## Python

```python
import prsmfile

with prsmfile.open("examples/example.prism") as pf:
    for a in pf.analyses():
        print(prsmfile.read_analysis(pf, a).to_dict())
```

`read_analysis` returns a `Report` with a `kind` (`structured`, `generic` or `not_calculated`),
a list of `Section`s (title, columns, rows, optional note) and warnings. `pf.analyses()` returns
copies: changing `a.results` or `a.parameters` does not affect later calls.

Raw data tables and rendered result tables:

```python
with prsmfile.open("examples/example.prism") as pf:
    for sheet_id in pf.data_tables():           # raw data tables, in the listed order
        table = prsmfile.read_table(pf, sheet_id)  # Table: title, columns, rows (strings)
    a = pf.analyses()[0]
    for name, data_sheet_id in a.views:         # Prism's rendered result views of an analysis
        table = pf.result_table(data_sheet_id)  # None if the sheet is not a result view
```

Readers live in a registry, `prsmfile.readers.REGISTRY` (analysis class to function).
`prsmfile.readers.register("CLASS")` adds one for the whole process, and registering a class that
already has a reader replaces it (see `docs/readers.md`).

## Supported analyses

Structured readers (named columns, p-values with their bounds and significance) exist for five
analysis families:

- t tests and nonparametric two-sample tests (Welch, unpaired, paired, Mann-Whitney, Wilcoxon)
- one-way ANOVA (ordinary and repeated measures)
- two-way ANOVA (ordinary, repeated measures GLM, mixed model REML)
- nonlinear regression
- area under curve

Every other analysis class, and every analysis whose stored layout a structured reader cannot
handle, goes through a generic reader that lists all stored values as `path, value` rows. A
structured reader adds an "Other values" section with the stored values it has no column for,
so nothing is dropped silently.

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
- Archives are read with size limits against zip bombs (100,000 members, 512 MiB per member,
  4 GiB in total, compression ratio 200 above 10 MiB). Real Prism files stay far below them. A
  file over a limit is rejected with an error naming the member.
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

## Reporting problems

Open an issue with the Prism version and, if possible, a file with invented data.

## Citing

See `CITATION.cff`.

## License

MIT, see `LICENSE`.
