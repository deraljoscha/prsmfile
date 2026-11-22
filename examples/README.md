# Example file

`example.prism` is a synthetic file in Prism's format. It was **not saved by Prism**: the script
`scripts/make_example.py` builds it with the test helper `tests/builder.py`. All data are
invented lab-style numbers, there is no real person or experiment behind them, and the file
carries only the user name `prsmfile-example` and no paths.

It holds five analyses over four data tables:

1. Welch's t test (two groups, n = 6)
2. ordinary one-way ANOVA with Tukey comparisons (three groups, n = 6)
3. normality tests (Shapiro-Wilk), a class without a dedicated reader, shown by the generic reader
4. ordinary two-way ANOVA (2 x 3, n = 4) with Bonferroni-Sidak comparisons
5. area under one curve

Every stored statistic is computed from the data in the script, with scipy 1.18.1 and
statsmodels 0.15.0 (development-only tools, not dependencies of prsmfile). The script header
says which library computed which number. To regenerate the file:

```
uv run --with scipy==1.18.1 --with statsmodels==0.15.0 --with numpy==2.5.5 --with pandas==3.1.1 --with patsy==1.0.3 python scripts/make_example.py
```

With exactly these pinned versions the output is byte-identical on every run (the zip
metadata is fixed too). Other library versions can change the last digits of a statistic and
then the bytes. `tests/test_examples.py` reads the file and checks
the key values against the numbers the script computes.

Try it:

```
prsmfile examples/example.prism --list
prsmfile examples/example.prism --analysis 02
```
