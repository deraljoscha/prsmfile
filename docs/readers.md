# Writing a reader

A reader turns the stored `results.json` of one analysis class into uniform sections.
The registry in `src/prsmfile/readers/__init__.py` maps `analysisClass` to a reader; classes
without one use the generic reader.

1. Add one module in `src/prsmfile/readers/`, for example `survival.py`, and import it at the
   bottom of `readers/__init__.py`.
2. Register a function with the class name:

   ```python
   from ..report import Section
   from . import register

   @register("SURVIVAL")
   def read_survival(pf, a, warn):
       ...
       return [Section("Title", ["col1", "col2"], rows, note=None)]
   ```

   `a` is the `Analysis` (`a.results`, `a.parameters`, `a.inputs`), `warn(msg)` records a
   warning on the report. Raise `KeyError` or `TypeError` if the layout is not what the reader
   expects: `read_analysis` then falls back to the generic reader and adds a warning.
3. Read every field defensively. Use `entries`, `label` and `num` from `prsmfile.values`:
   `num` turns `"undefined"` and other non-numbers into `None`, `entries` iterates the
   hash-keyed collections in `results.json`, `label` formats a stored id.
4. Every row of a section must have exactly `len(columns)` cells.
5. Add a synthetic test with `PrismBuilder` (`tests/builder.py`) and call
   `assert_sections_well_formed(report)` from `tests/helpers.py`.
6. Run `pytest -q`, then the corpus tests with `pytest -q tests/test_corpus.py -s` and check
   the printed counts (see the README for fetching the corpus).

Details of the stored layout for each class are in `docs/format.md`, section 2.
