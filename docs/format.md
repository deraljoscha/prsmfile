# GraphPad Prism 10/11 `.prism` file format (empirical specification)

Status: derived by inspection of 75 public CC-BY/CC0 files from 27 Zenodo records
(Prism 10.0.0 to 11.1.0 writers, 2023 to 2025). No vendor documentation was used.
Everything below is observed behavior; "n of m" counts refer to this corpus.
Corpus totals: 75 archives, 41,210 zip entries (35,066 files + 6,144 directory entries),
549 analyses, 1,742 data sheets, 19,156 data sets, 1,699 `data.csv` tables, 75 `document.json`.

Conventions: `<id>` = a UUID used as a JSON key or path segment. Folder ids are upper-case
UUIDs. Dict keys inside `results.json` are lower-case UUID-shaped hashes (see 3.5).
Paths in JSON are written `a/b[]/c` (`[]` = array element).

## 1. Container and object model

### 1.1 Zip container

- Plain zip, no zip64, no encryption, no nested zips, no duplicate entry names, all entry
  names ASCII, create_system = Unix (3), general-purpose flag bits = 4.
- Compression: every file entry is DEFLATE (method 8), 35,066 of 35,066. Directory entries
  (`analyses/`, `data/sets/` ...) exist and are method 0 size 0. The earlier assumption "store" is
  wrong for this corpus. `zipfile` handles it transparently.
- JSON members: UTF-8, no BOM (0 of 26,959), LF, tab-indented, start with `{`. 107 contain raw
  non-ASCII (UTF-8), 2 contain `\uXXXX` escapes; both decode with `json.loads`.
- Size profile: median archive 0.47 MB uncompressed; max 212.8 MB (`22981103_0`, 40.8 MB zipped)
  because of 7 files carrying `media/*.emf|svg|pdf` (emf 96 MB, svg 95 MB). Largest JSON member
  is a `results.json` of 354 KB, largest `sheet.json` 182 KB, largest `data.csv` 898 KB. A reader
  must open members lazily and never touch `media/` or `*.bin` unless asked.

### 1.2 Top-level layout

| Path | Files in corpus (archives) | Meaning |
|---|---|---|
| `document.json` | 75 (75) | root document, sheet index, UI state |
| `data/sheets/<id>/sheet.json` | 1,742 (75) | one `DataSheet` per table, raw and result |
| `data/sets/<id>.json` | 19,156 (75) | one `DataSet` (a column group), titles and types |
| `data/tables/<id>/data.csv` | 1,699 (75) | cell values, headerless |
| `data/tables/<id>/content.json` | 1,699 (75) | `{numberOfColumns, numberOfRows, version}` |
| `data/tables/<id>/data.dt` | 1,704 (75) | 32 hex chars, opaque change token (not md5 of the csv); ignore |
| `analyses/<id>/sheet.json` | 549 (54) | analysis header, input and result links |
| `analyses/<id>/parameters.json` | 549 (54) | analysis settings |
| `analyses/<id>/results.json` | 549 (54) | machine-readable statistics |
| `analyses/<id>/result_sheets/<id>.json` | 1,054 (54) | `AnalysisView`: points to a result data sheet |
| `analyses/<id>/floating_notes/<id>.json` | 211 (22) | notes (e.g. auto warnings) |
| `graphs/<id>/sheet.json` | 627 (71) | `FENGraphSheet` (title, floatingNotes, inputDataSets) |
| `graphs/<id>/data.bin` | 627 (71) | binary graph (magic `PCFFGRA4`), opaque |
| `info/<id>/sheet.json` | 87 (58) | `InfoSheet`: `experimentDate`, `notesText`, `constants[{name,value}]` |
| `layouts/<id>/sheet.json`, `data.bin`, `preview.png` | 29 (9), 33 (11), 3 (3) | `FENLayoutSheet`, opaque binary |
| `media/<id>.{emf,pdf,svg,png}` | 977, 1140, 301, 3 (all in 7 archives) | embedded images, referenced by graphs/layouts |
| `misc/<id>.bin` | 995 (58) | opaque binary (little-endian structs, no magic) |

Binary members (`*.bin`, `*.emf`, ...) are not needed for statistics; treat as opaque.

### 1.3 `document.json`
All 75 files have these keys (counts: `compatibility` 66, `customColors` 21, rest 75):
```
@class="Document", $id="document.schema.json", creationDate, modificationDate (ISO-8601 Z),
createdBy{name="Prism", user, version, platform}, modifiedBy{same shape},
formatVersion, minFormatVersion, minPrismVersion,
compatibility[{formatVersion, action}],          // 66 of 75
sheets{graphs[], analyses[], info[], data[], layouts[]},   // lists of folder ids (see below)
uiSettings{currentSheetType, viewMode, nextDataSheetNumber, currentSheets{...}, ...},
sheetAttributesMap{<sheetId>: {title, highlightColor?}},
customColors[]                                    // 21 of 75
```

Version spread: `formatVersion` 1-0-0 (4 files), 1-0-1 (3), 1-1-0 (12), 1-2-0 (14), 1-3-0 (5), 1-4-0 (1),
1-4-1 (15), 1-5-0 (6), 1-5-1 (1), 1-6-0 (5), 1-6-1 (9). `minFormatVersion` ranges 1-0-0 to 1-5-0,
`minPrismVersion` is one of 10.0.0, 10.0.3, 10.1.0, 10.3.0, 10.5.0. Versions are dash-separated strings.

`createdBy.version` / `modifiedBy.version` are four-part dotted strings (`10.0.0.153` to
`11.1.0.224`). Prism 11.x files use formatVersion 1-6-1 and minFormatVersion 1-2-0/1-4-0, so there
is no format break between 10 and 11. Compare versions as integer tuples
(`tuple(map(int, s.split('-')))`). A reader should accept any `1-x-y` and warn on major != 1.

`document.sheets` lists the **user-visible** sheets only:

| key | ids listed | folders present on disk | note |
|---|---|---|---|
| data | 687 | 1,742 sheets | the other 1,055 data sheets are result tables (see 1.5) |
| analyses | 545 | 549 | 4 analyses exist on disk but are not listed (hidden/orphans) |
| graphs | 621 | 627 | 6 not listed |
| info | 87 | 87 | |
| layouts | 29 | 29 | |

Titles of listed sheets are in `sheetAttributesMap[id].title`, and also in each `sheet.json.title`.
Do not trust the document lists for discovery; enumerate `analyses/*/sheet.json` etc.

### 1.4 How things link (ids)
```
document.json
  sheets.data[]  -> data/sheets/<S>/sheet.json            (raw data tables, user sheets)
  sheets.analyses[] -> analyses/<A>/sheet.json

data/sheets/<S>/sheet.json    (@class "DataSheet")
  title                           sheet title (str)
  table.uid  = <T>                -> data/tables/<T>/data.csv + content.json   (T != S!)
  table.format                    "column"|"xy"|"grouped"|"contingency"|"survival"|"parts_of_whole"|"view"
  table.dataFormat                "y_single"|"y_replicates"|"y_sd_n"|"y_sd"|"y_se"|"y_plus_minus"|"text"
  table.dataSets[]                ordered ids -> data/sets/<D>.json   (the columns / column groups)
  table.xDataSet, xDataSetFormat  (XYDataTable only, 446 of 1,742)
  table.rowTitlesDataSet          (1,009 of 1,742)
  table.replicatesCount           (309)   table.subcolumnTitlesDataSet (15)
  table.valuesStorageData (51), dataValuesSource (1)

analyses/<A>/sheet.json   (@class "AnalysisSheet")
  title, analysisClass, isCalculated, isAllDataAnalyzed, currentResultSheet,
  preferredResultSheet, minRequiredVersion{major,minor,subminor,build}
  resultSheets[{uid:<V>, title}]            -> analyses/<A>/result_sheets/<V>.json
  inputSheets[{uid:<S>, title}]             -> data/sheets/<S> (the analysed table)
  inputDataSets[{uid:<D>, title, idx:"A"}]  -> data/sets/<D>.json (analysed columns)

analyses/<A>/result_sheets/<V>.json   (@class "AnalysisView")
  name, viewIdx, dataSheet=<R>            -> data/sheets/<R>/sheet.json  (RESULT data sheet)
  isVisible, isInternal, graphId, tabState, ... (textBlocks[], graphDefaults, isGraphData, useGraphData optional)
```

Resolution chain to a rendered result table: `analyses/<A>/result_sheets/<V>.json.dataSheet = R`,
then `data/sheets/<R>/sheet.json.table.uid = T`, then `data/tables/<T>/data.csv`.

Link integrity in the corpus:
- 1,050 of 1,054 views have `dataSheet`; all 1,050 resolve to an existing `data/sheets/<R>`.
  The 4 without are graph-only or text-block views (`graphId`, `textBlocks`).
- 966 of 1,050 result sheets have a `data.csv`; 84 do not (their `table.uid` has no folder at all;
  they are derived "view" tables that Prism recomputes, e.g. "Row statistics ..."). Resolution
  must tolerate a missing table.
- `inputDataSets[].idx` is the spreadsheet letter (A, B, ...), `uid` is the data-set id. 1,983
  of 2,011 uids exist in `data/sets/`, 28 do not. 1 item is `null`. `inputSheets` is empty in 23 of
  549 analyses and points to a non-user data sheet in 8 (analysis chained to a result table) and
  to a missing sheet in 1.
- In `results.json`, `id.col.idx` equals the position of `id.col.uid` in the input sheet's
  `table.dataSets` in 5,336 of 5,337 cases (1 uid not in the sheet). So `idx` is a 0-based
  column index into `dataSets`, not into the csv.
- `analyses/<A>/sheet.json` also has `alertText` (57, concatenated summary and warning text), `isCustomTitle` (113),
  `pairwiseComparisonsDataUid` (266), `floatingNotes` (179), `defaultResultSheet` (126).

### 1.5 Raw data tables versus result tables
Decide by link, not by name or by `format`:

| class | rule | count |
|---|---|---|
| raw (user) data table | sheet id is in `document.sheets.data` (none is referenced by a view) | 687 |
| result table | sheet id is referenced as `AnalysisView.dataSheet` | 1,050 (989 `format=view`, 61 `format` column/xy) |
| orphan data sheet | neither of the above | 5 |

Within result tables:
- `format=view`, `dataFormat=text` (683): the rendered report, a free-form grid of text.
- `format=view` with `y_single|y_replicates|y_sd_n|y_se|y_plus_minus` (306): numeric derived data
  (curve points, estimation-plot data, row statistics); often no csv on disk (84).
- `format=column`, `dataFormat=text` (32) and `column`/`xy` numeric ones (29): also report text or
  real derived data (descriptive statistics, simple regression, survival, T-test side tables).
  They are still result sheets; do not list them as user data.

Distinguishing signals for raw tables: `table.format` in {column, xy, grouped, contingency,
survival, parts_of_whole} AND listed in `document.sheets.data`. `format=view` never occurs in the
user list. Result sheet titles have the pattern `"<analysis title>:<view name>"`
(e.g. `Welch's t test of X:Tabular results`); raw sheet titles are plain.

### 1.6 Titles and column headers
`data.csv` has **no header row** and no row/column titles. Headers come from the data-set files.

`data/sets/<D>.json` (`@class "DataSet"`, 19,156):

| field | presence | notes |
|---|---|---|
| `uid`, `fenID`, `format`, `$id` | 19,156 | `format` in y_replicates 11,768; text 4,021; y_single 2,955; y_sd_n 220; series 96; y_plus_minus 46; y_sd 17; text_replicates 15; y_se 12; date_se 3; y_errorBar 3 |
| `title` | 5,219 | 3 shapes: absent (13,937, unnamed column), `str` (3,717) or object `{string, version, formatting[{range, attributes}]}` (1,502). Use `title.string` if dict. Strings can contain `\r` (line breaks inside headers). |
| `replicates[]` | 7,506 | list of per-subcolumn descriptors: `{@class DriverReplicate\|SeriesReplicate, valueType "real\|int\|string\|date", firstRow, lastRow, significantDigitsCount, decimalsLength, commonAttributes[], cellAlignments?, cellAttributes?, cellTextFormats?, maxWidth?}` |
| `replicate ranges[]` | 11,635 | alternative encoding (key contains a space): `[{range:"0" or "1~3", replicate:{...}}]`; subcolumn count = max range end + 1 |

`valueType`: string 4,021, real 3,863, int 220, date 6, series real 96. A `series` data set
(replicate has `startValue`, `interval`) is a generated X column (row number sequence) and has
**no csv column**.

Unnamed data sets get Prism's default names (column letter A, B, ... by position); use
`inputDataSets[].idx` for analyses, else compute the letter from the index.

### 1.7 `data.csv` dialect and column layout
- RFC 4180 CSV: comma separator, `"` quote, `""` escape, UTF-8 (102 of 1,699 files contain non-ASCII,
  0 BOM), no header.
- Row terminator is `\n` (1,654 of 1,654 non-empty files end with LF). Cells can contain embedded
  `\r` (46 files; e.g. `"WT\r(3 weeks)"`), and embedded `,` is quoted
  (`"    Sum of positive, negative ranks","55.00 , 0.000"`). Open with `newline=''` and
  `csv.reader`; never `splitlines()`.
- Empty cell = missing value (empty string). 45 files are 0 bytes (empty tables; `numberOfRows` 0).
- Numbers are written with up to 17 significant digits (`0.0263000000000000005`,
  `3.00000000000000008e-06`), dates as `YYYY-MM-DD HH:MM:SS`. Raw numeric columns may mix shortened
  values (`0.312793`); parse with `float()`.
- `content.json.numberOfRows` equals the parsed row count in 1,654 of 1,654 non-empty tables.
  `numberOfColumns` equals the row width in 1,639 and is wrong in 15 (declared 0 in 13, 1 in 1, 2 in 1
  while rows are 6 to 36 wide). Trust the actual row width, not `content.json`.

Column order of a raw table (verified on all `format` variants; the formula below reproduces
`content.json.numberOfColumns` for 1,560 of 1,658 tables; the rest are mostly `view` tables whose
x column is not stored, plus 4 cases with surplus declared data sets):
```
[ rowTitlesDataSet column ]          if table.rowTitlesDataSet           (1 column, text)
[ xDataSet columns ]                 if table.xDataSet and its format != "series"
                                     (width 1; "date_se" and "y_errorBar" width 2)
for D in table.dataSets:             in listed order
    width(D) subcolumns              = len(replicates) or max(range end)+1
```

Subcolumn meaning by data-set `format` (width): `y_single` 1; `y_replicates` N (replicate
values, N = `table.replicatesCount` in 309 tables, otherwise per data set); `y_sd_n` 3 (mean, SD, N);
`y_sd` 2 (mean, SD); `y_se` 2 (mean, SEM); `y_plus_minus` 2 to 3 (mean, plus, minus; inferred);
`text` 1; `text_replicates` N.

Examples: grouped/y_replicates with `replicatesCount 10` and 3 data sets = row title + 30 value columns; xy/y_sd with row
titles and x = empty title cell, x, then (mean, SD) pairs; survival = row title, start date, end date, flag columns.

### 1.8 Result tables (rendered text) in `data.csv`
A report is a grid of text with free layout: section header rows, then indented label/value rows
(leading 2 to 4 spaces; strip for matching). Widths 2 to 9 columns. Numbers are rounded to
`parameters.json.content.output.significantDigitCount` (4 in all analyses of the five target
classes) and p-values are formatted strings (`<0.0001`, `0.0386`, `P=0.0386`, `ns`, `****`).
They are useful as a fallback but **lossy**; prefer `results.json`.

Common `AnalysisView.name` values: `ANOVA results` + `Multiple comparisons` (ANOVA), `Tabular results`
(+ `Estimation Plot`) (t tests), `Table of results` + `Curve` (nonlinear regression), `Area under curve`.

## 2. Analyses: classes, `parameters.json`, `results.json`

### 2.1 Common shape

`analysisClass` distribution (549 analyses): T_TESTS_AND_NONPARAMETRIC 125, ONE_WAY_ANOVA 103,
NONLINEAR_REGRESSION 79, AREA_UNDER_CURVE 78, TWO_WAY_ANOVA 44, NORMALITY_TESTS 37,
ROW_STATISTICS 16, MULTIPLE_TWO_SAMPLE_TESTS 12, DESCRIPTIVE_STATISTICS 13, INTERPOLATION 11,
SIMPLE_LINEAR_REGRESSION 6, TRNSFORM 6 (sic), SURVIVAL 7, REMOVE_BASELINE 5, CORRELATION 3,
CONTINGENCY_TABLE 1, FREQUENCY_DISTRIBUTION 1, IDENTIFY_OUTLIERS 1.

`parameters.json`:
```
{ "@class":"AnalysisParameters", "$id":"analyses/<class_snake>/parameters.schema.json",
  "version":"0.0.0"|"0.0.1", "analysisClass"?: "...", "content": { ... } }
```
`analysisClass` inside parameters is present in only some files (47 of 103 ANOVA, 82 of 125 t tests,
49 of 79 NLR, 78 of 78 AUC); take the class from `sheet.json`. `$id` encodes the class
(`analyses/one_way_anova/`, `two_way_anova/`, `two_sample_tests/`, `nonlinear_regression/`,
`area_under_curve/`). Missing numbers in parameters are the string `"undefined"` (e.g.
`data.range.minX.value`, `flagging.*.threshold`).

`results.json`:
```
{ "@class":"AnalysisResults", "$id":"analyses/<class>/results.schema.json", "version":"0.0.0",
  "content": { "status": {"error":"VALID","warning":[]}, "<modelKey>": {...}, ... } }
```
- `results.json` exists for all 549 analyses. If the analysis has no stored results it is the stub
  `{"@class":"AnalysisResults"}` (no `$id`, no `version`, no `content`): 126 stubs.
- Result `version`: 0.0.0 almost everywhere; two_sample_tests 0.0.2 (18), two_way_anova 0.1.0 (30) and
  0.1.1 (4), survival 0.0.1 (1). Treat as additive.

Common nodes:

| Node | Shape |
|---|---|
| p-value | `{value: float, level: float (alpha), isSignificant: bool, state: "P_VALUE_EQUAL"\|"P_VALUE_GREATER"}` |
| confidence interval | `{lower, upper, level}`; `level` is a percent (`95.0`), except 3 REML CIs where it is `0.05` |
| column id | `{col:{uid, title, idx}}`, two-way adds `row:{idx,title}`, NLR adds `model:{name,title}` |
| keyed collection | `{<hash>: {id:{...}, value:<payload>}}` (iterate `.values()`, see 3.5) |

`descriptiveStatistics` (ANOVA: 84 of 86, t tests: 96 of 96 with content; a payload per analysed
data set): `{n, mean, sd, meanSE, meanCI{lower,upper,level}, minimum, firstQuartile, median,
thirdQuartile, maximum, missing?}` (`missing` in 1 analysis only). Key shape differs: ANOVA uses
hash keys, t tests use the literal keys `sample1`, `sample2` (+ `differences` in 43 of 96, the stats
of the pair differences).

### 2.2 T_TESTS_AND_NONPARAMETRIC (125 analyses; 96 with `content`)
`parameters.content` fields that matter:

| path | values (counts of 125) |
|---|---|
| `experimentalDesign` | WELCH_T_TEST 44, PAIRED_T_TEST 39, UNPAIRED_T_TEST 20, MANN_WHITNEY_TEST 12, WILCOXON_TEST 9, KOLMOGOROV_SMIRNOV_TEST 1 |
| `options.pValueTailType` | P_VALUE_TWO_TAILED 111, P_VALUE_ONE_TAILED 14 |
| `options.swapDirection` | true 122, false 3 (see direction note) |

Design to `content` model key (96 with content):

| design | model key in `content` | n |
|---|---|---|
| WELCH_T_TEST | `welchTTestModel` | 25 (19 more have stub results) |
| UNPAIRED_T_TEST | `unpairedTTestModel` | 18 (2 stubs) |
| PAIRED_T_TEST | `pairedTTestModel` | 35 (4 stubs) |
| MANN_WHITNEY_TEST | `mannWhitneyTestModel` | 10 (2 stubs) |
| WILCOXON_TEST | `wilcoxonTestModel` | 8 (1 stub) |
| KOLMOGOROV_SMIRNOV_TEST | none in corpus (stub) | 0 |

Other content keys: `descriptiveStatistics` 96, `compactLetterDisplay` 78, `status` 96 (with
`warning[]`: `MEAN_VALUES_ANALYZED` 1).

Key statistics (all numbers are JSON floats; `n*` ints):

| statistic | path under `content` | n |
|---|---|---|
| Welch t, df, p | `welchTTestModel.welchTTest.{t, df, pValue{...}, status}` | 25 |
| Unpaired t, df, p | `unpairedTTestModel.unpairedTTest.{t, df, pValue, status}` | 18 |
| means, n, difference, SE, CI, R2 | `{welch,unpaired}TTestModel.differenceOfMeans.{n1,mean1,n2,mean2,difference,stdErrorOfDifference,confidenceIntervalOfDifference{lower,upper,level},rSquared}` | 43 |
| Paired t, df, p | `pairedTTestModel.pairedTTest.{t,df,pValue}` | 35 |
| mean difference, SD, SE, CI, R2 | `pairedTTestModel.meanOfDifferences.{mean,stdDeviationOfDifferences,stdErrorOfDifferences,confidenceIntervalOfDifferences{lower,upper,level},rSquared}` | 35 |
| Mann-Whitney U, ranks, p | `mannWhitneyTestModel.mannWhitneyTest.{U, sumRanks1, sumRanks2, meanRanks1, meanRanks2, differenceOfRankMeans, pValue, pValueExact, pValueApproximate, tiesStatus (NO_TIES/WITH_TIES), status}` | 10 |
| Wilcoxon W, p | `wilcoxonTestModel.wilcoxonTest.{signedRanksSum, positiveRanksSum, negativeRanksSum, n, tieCount, zeroesStatus (NO_ZEROES), pValue, pValueExact, pValueApproximate, status}` | 8 |
| letters | `compactLetterDisplay.{letterCount, sampleCount, samples{<h>:{id,value:"A"}}}` | 78 |

Also present: `{welch,unpaired}TTestModel.varianceTest.{f,dfNumerator,dfDenominator,pValue,status}` (25 + 17 of 18),
`pairedTTestModel.pearsonTest.{r,pValue,pValueOneTailed}`, `mannWhitneyTestModel.differenceOfMedians.{median1,median2,hodgesLehmannDifference}`,
`wilcoxonTestModel.medianOfDifferences.median` and `.spearmanTest`.

`pValue` is the primary one; `pValueExact` / `pValueApproximate` are given in addition for rank
tests (in the sample `pValue` equals `pValueExact`). There are no post tests in this class.

Direction note (verified in 43 of 43 unpaired/Welch analyses, all with `swapDirection` true):
`mean1`/`n1` belong to `inputDataSets[0]` (column A) and `mean2`/`n2` to `inputDataSets[1]`;
`difference` = `mean2 - mean1` (B minus A), matching the rendered line
`Difference between means (B - A) ± SEM`. In `descriptiveStatistics`, `sample1` is the
SECOND input column (idx 1) and `sample2` the first. For paired tests the mean of differences
equals `sample1.mean - sample2.mean` in 35 of 35. Use `id.col.uid` to attach names, never the key
order, and do not recompute the sign without checking `swapDirection` (no unpaired case with
`swapDirection` false exists in the corpus to verify the other direction).

Shortened excerpt (Welch, `12189101_0`, trimmed; real values):
```json
{"content":{"status":{"error":"VALID","warning":[]},
 "welchTTestModel":{"welchTTest":{"status":"VALID","t":6.028425312263046,"df":57.32806195490326,
   "pValue":{"value":1.2689678155570057e-07,"level":0.05,"isSignificant":true,"state":"P_VALUE_EQUAL"}},
  "differenceOfMeans":{"n1":30,"mean1":5307.3,"n2":30,"mean2":1934.4666666666667,"difference":-3372.8333333333335,
   "stdErrorOfDifference":559.4882840253993,"confidenceIntervalOfDifference":{"lower":-4493.05,"upper":-2252.62,"level":95.0}}},
 "descriptiveStatistics":{"sample1":{"id":{"col":{"uid":"5BC4B6C3-...","title":"Evolved","idx":1}},"value":{"n":30,"mean":1934.47,"sd":2046.23}},
                          "sample2":{"id":{"col":{"uid":"E5BD9D51-...","title":"Ancestral","idx":0}},"value":{"n":30,"mean":5307.3}}}}}
```

### 2.3 ONE_WAY_ANOVA (103 analyses; 86 with `content`)
`parameters.content` (counts of 103):

| path | values |
|---|---|
| `experimentalDesign` | ORDINARY_ANOVA 101, REPEATED_MEASURES_ANOVA 2 |
| `repeatedMeasures.method` | OPTIONAL 102, GLM 1 (other sub-fields constant) |
| `postTests.type` | PAIRWISE_TESTS 92, NO_TESTS 11 |
| `postTests.pairwiseTests.pairwiseDesign.type` | ALL_VS_ALL 58, CONTROL_VS_ALL 32, NO_TESTS 11, SELECTED_VS_SELECTED 2 |
| `...multipleComparisons.type` | STATISTICAL 93, NO_CORRECTION 10 (selects the active sub-block; all sub-blocks are always written) |
| `...multipleComparisons.statistical.test` | TUKEY 68, HOLM_SIDAK 13, NO_TEST 11, DUNNET 10, BONFERRONI_SIDAK 1 |

Beware: `multipleComparisons.type` and `statistical.test` can disagree with the result (one file had
`type=NO_CORRECTION` next to `test=TUKEY`). Read the applied method from
`results.json ...multipleComparisons.method` (string: `Tukey` 50, `Holm-Šídák` 12, `No correction` 9,
`Dunnett` 4, `Bonferroni-Šídák` 1 of 76; note the non-ASCII letters).

No Kruskal-Wallis or nonparametric one-way design occurs in this corpus.

`content` keys: `status`, `descriptiveStatistics` (84), `ordinaryAnovaModel` (83) or
`repeatedMeasuresGlmAnovaModel` (1); 2 analyses have `content` without any model (error
`INVALID_DATA_RM_MISSING_SUBJECT_VAL`, `INVALID_DATA_TOO_FEW_COLUMNS`).

`ordinaryAnovaModel` key statistics:

| statistic | path | n of 83 |
|---|---|---|
| model status | `status` | 83 (`VALID`) |
| F, dfs, p, SS, MS, R2 | `anovaTable.colFactor.{ss,df,ms,r2,fTest{f,dfNumerator,dfDenominator,pValue,status}}` | 82 |
| residual and total | `anovaTable.residual.{ss,df,ms}`, `anovaTable.total.{ss,df}` | 82 |
| levels, points | `dataSummary.{levelCount, pointCount}` | 82 |
| Bartlett | `bartlettTest.{statistic, pValue, status}`; statistic and p only when status `VALID` | status 81 (VALID 48, TOO_FEW_POINTS 25, SD_ZERO 8) |
| Brown-Forsythe | `brownForsytheTest.{f,dfNumerator,dfDenominator,pValue,status}` | 81 |
| multiple comparisons header | `multipleComparisons.{status, method, comparisonCount, significantCount}` | 76 |
| each pair | `multipleComparisons.tests.<h1>.value.<h2>.value.{meansDifference, meansDifferenceSE, meansDifferenceCI{...}, statistic (q or t), df, pValueAdjusted, pValueIndividual, sample1{id,value{mean,n}}, sample2{...}, status}` | 76 analyses, 730 pairs |
| letters | `compactLetterDisplay.{letterCount,sampleCount,samples{<h>:{id,value}}}`; value like `"A"`, `"A B"` | 26 |

Per pair: `meansDifferenceCI` is present in 64 of 76 analyses, `pValueAdjusted` in 67 and
`pValueIndividual` in 9 (method `No correction` has only `pValueIndividual`, adjusted methods
mostly only `pValueAdjusted`; Tukey and Bonferroni families occasionally both).
The outer key `<h1>` is the sample1 column, the inner `<h2>` the sample2 column; difference =
`sample1.mean - sample2.mean` (e.g. `-4.3125 = 3.055 - 7.3675`). With ALL_VS_ALL the first sample is
the lower column index in the example inspected; CONTROL_VS_ALL puts the control first.

Repeated-measures (1 analysis, `repeatedMeasuresGlmAnovaModel`): same `anovaTable` plus
`matchedFactor.{ss,df,ms,r2,fTest}`, `colFactor.ggEpsilon`, `matchingTest.{f,dfNumerator,dfDenominator,pValue}`,
`dataSummary.{levelCount, matchedCount, missingCount}`.

Excerpt (Tukey, `15285264_0`, trimmed):
```json
{"content":{"status":{"error":"VALID","warning":[]},
 "ordinaryAnovaModel":{"anovaTable":{"colFactor":{"ss":52.40,"df":3.0,"ms":17.47,
     "fTest":{"f":3.8437628503724985,"dfNumerator":3.0,"dfDenominator":12.0,
      "pValue":{"value":0.0386400349069928,"level":0.05,"isSignificant":true,"state":"P_VALUE_EQUAL"}}},
   "residual":{"ss":54.53,"df":12.0,"ms":4.544},"total":{"ss":106.9,"df":15.0}},
  "multipleComparisons":{"method":"Tukey","comparisonCount":6,"tests":{"<h1>":{"id":{"col":{"title":"ctrl","idx":0}},
   "value":{"<h2>":{"id":{"col":{"title":"asp","idx":1}},"value":{"meansDifference":-4.3125,"meansDifferenceSE":1.507,
     "meansDifferenceCI":{"lower":-8.788,"upper":0.1628,"level":95.0},"statistic":4.0459,"df":12.0,
     "pValueAdjusted":{"value":0.0602,"level":0.05,"isSignificant":false,"state":"P_VALUE_EQUAL"},
     "sample1":{"value":{"mean":3.055,"n":4}},"sample2":{"value":{"mean":7.3675,"n":4}}}}}}}}}}}
```

### 2.4 TWO_WAY_ANOVA (44 analyses; 34 with `content`)
`parameters.content`:

| path | values (of 44) |
|---|---|
| `experimentalDesign` | ORDINARY_ANOVA 22, REPEATED_MEASURES_BY_ROWS 9, REPEATED_MEASURES_BY_BOTH_FACTORS 7, REPEATED_MEASURES_BY_COLS 6 |
| `repeatedMeasures.method` | OPTIONAL 42, REML 2; `assumeSphericity` true 19 / false 25 |
| `postTests.type` | PAIRWISE_TESTS 41, NO_TESTS 3 |
| `postTests.pairwiseTests.meansDesignType` | `COMPARE_CELLS_BY_COLUMNS_WITHIN_ROWS_SINGLE_FAMILY` 20, `COMPARE_CELLS_DIFFER_BY_ONE_FACTOR_SEPARATE_...` 10, `COMPARE_CELLS_BY_ROWS_WITHIN_COLUMNS_SEPARATE_...` 4, `NO_TESTS` 3, `COMPARE_CELLS_DIFFER_BY_ONE_FACTOR_SINGLE_...` 3, `COMPARE_CELLS_BY_ROWS_WITHIN_COLUMNS_SINGLE_...` 3, `COMPARE_CELLS` 1 (suffixes cut at 40 characters in the survey; read the full string) |
| `...multipleComparisons.type` / `statistical.test` | STATISTICAL 31 / NO_CORRECTION 13; TUKEY 15, BONFERRONI_SIDAK 12, BONFERRONI_DUNN 7, NO_TEST 7, HOLM_SIDAK 3 |

Design to model key (34 with content): ORDINARY -> `ordinaryAnovaModel` (15), RM by both or by
cols -> `repeatedMeasuresGlmAnovaModel` (13), RM by rows -> `repeatedMeasuresGlmAnovaModel` (4) or
`repeatedMeasuresRemlAnovaModel` (2, the two analyses with `repeatedMeasures.method` REML).
Stub results: 7 ORDINARY + 3 RM-by-rows.

`<model>` = ordinary / GLM / REML key. Statistics:

| statistic | path under `<model>` | present |
|---|---|---|
| main effects and interaction | `anovaTable.{rowFactor, colFactor, rowFactorVsColFactor}.{ss, df, ms, variation (percent of total), fTest{f,dfNumerator,dfDenominator,pValue,status}}` | ordinary 15, GLM 17 |
| residual | `anovaTable.residual.{ss,df,ms}` (ordinary: `total.{ss,df}` only in 3 of 15) | |
| REML fixed effects | `fixedEffects.{rowFactor,colFactor,rowFactorVsColFactor}.fTest{f,dfNumerator,dfDenominator,pValue,status}` (REML has no `anovaTable`) | 2 of 2 |
| matching test (REML) | `matchingTest.{chiSquared, df, pValue, status}` | 2 of 2 |
| data summary | `dataSummary.{rowCount, colCount, pointCount, isBalancedDesign}` (ordinary); `{rowCount, colCount, matchedCount, missingCount}` (RM) | |
| means | `means.{total, rows.<h>.{id{row},value}, cols.<h>.{value}, cells.<h>.{id, value.<h>.{id, value}}}` | `report.means` true in 4 analyses; present in 4 ordinary, 17 GLM, 2 REML |
| multiple comparisons header | `multipleComparisons.{status, method, familyCount, comparisonPerFamilyCount}` | ordinary 13, GLM 17, REML 2 |
| each cell comparison | `multipleComparisons.tests.<h1>.value.<h2>.value.{meansDifference, meansDifferenceSE, meansDifferenceCI, statistic, df, pValueAdjusted or pValueIndividual, sample1{id,value{mean,n}}, sample2{...}, status}` | |
| letters | `compactLetterDisplay` (1 of 34, ordinary, ids are `row` only) | |

The ids carry both factors: `id = {col:{uid,title,idx}, row:{idx,title}}` for a cell; `{row}` only
for a row; `{col}` only for a column. `row.idx` is the 0-based row of the input sheet, `row.title`
its row title. Adjusted p-values appear under adjusted families, `pValueIndividual` under
`No correction`. Quirk: in REML `differenceCI.level` is `0.05` (alpha) instead of `95.0` (3
occurrences).

Excerpt (RM GLM, Sidak, `18623500_0`, trimmed):
```json
{"content":{"repeatedMeasuresGlmAnovaModel":{"anovaTable":{
   "rowFactor":{"ss":2.9036,"df":1.0,"ms":2.9036,"variation":13.3345,
     "fTest":{"f":6.0054,"dfNumerator":1.0,"dfDenominator":6.0,
      "pValue":{"value":0.049749816286736144,"level":0.05,"isSignificant":true,"state":"P_VALUE_EQUAL"}}},
   "colFactor":{"...":"same shape"},"rowFactorVsColFactor":{"...":"same shape"},"residual":{"ss":14.769,"df":6.0,"ms":2.4615}},
  "multipleComparisons":{"method":"Bonferroni-Šídák","familyCount":1,"tests":{"<h1>":{"id":{"col":{"idx":0},"row":{"idx":0,"title":"APPNL-G-F"}},
    "value":{"<h2>":{"id":{"col":{"idx":1},"row":{"idx":0}},"value":{"meansDifference":0.7025,"statistic":0.6332,"df":6.0,
     "pValueAdjusted":{"value":0.7974,"isSignificant":false},"sample1":{"value":{"mean":2.29,"n":4}}}}}}}}}}}
```
(`    Genotype,2.904,1,2.904,"F (1, 6) = 6.005",P=0.0497`.)

### 2.5 NONLINEAR_REGRESSION (79 analyses; 72 with `content`, 70 isCalculated true + 2 missing)
`parameters.content` fields that matter:

| path | values (of 79) |
|---|---|
| `model.equation.name`, `.definition` (with `\r\n`), `.parameters[]` | One phase decay 42 (Y0, Plateau, K); Sigmoidal 4PL X is concentration 23 (Bottom, Top, IC50, HillSlope); log(agonist) vs response variable slope 9; log(inhibitor) 1; Line through point 2; Line 1; Quadratic 1 |
| `model.constraints.<param>.{type, value}` | CONST, GREATER, LESS (e.g. `Plateau CONST 42`, `K GREATER 42`) |

`results.content` keys: `status` 72, `dataSummary` 72, `models` 72, `modelComparison` 7, `outliers` 1.
`status.warning[]`: `INCOMPLETE_CI` 24, `UNSTABLE_PARAMETERS` 6 (4 together with INCOMPLETE_CI).

Structure: `models.<h>` is one entry per (data set column x model):
`id = {col:{uid,title,idx}, model:{name:"Model 1", title:"<model description>"}}`.

| statistic | path under `models.<h>` | present |
|---|---|---|
| fit status | `value.status` (COMPLETED, INTERRUPTED, ...) | 72 |
| best-fit value | `value.parameters.<NAME>.<h0>.value.estimate` | per parameter |
| SE | `...value.se` (absent for derived parameters, `"undefined"` for CONSTANT) | e.g. K 40 of 42 |
| CI | `...value.ci.{lower,upper,level}` (`lower`/`upper` can be `"undefined"`; 847 lower and 911 upper in corpus) | |
| R2 | `value.goodnessOfFit.r2.<h0>.value` | 70 |
| adjusted R2 | `value.goodnessOfFit.adjR2` | 70 |
| Sy.x, RMSE, AICc | `goodnessOfFit.{syx (69), rmse (69), aicc (70)}` (`aicc` can be `"undefined"`) | |
| correlation matrix of parameters | `value.covariance.<P1>.<P2>.<h0>.value` (1.0 on the diagonal, `"undefined"` when not computed; 1,344 such cells) | |
| n points | `dataSummary.<h>.{id, value{xValuesAnalyzed, yValuesAnalyzed, yValuesSkipped, outliersCount?}}` | 72 |
| model comparison | `modelComparison.<h>.{id[] (2 entries col+model), value.fTest{status, isRun, simpleModel{key,name,ss,df,status}, complexModel{...}, preferredModelKey, preferredModelName, summary{f,dfNumerator,dfDenominator,pValue}}}` | 7 |

Not in the table above: `value.equation.<h0>.value` (fitted equation string), `value.iterationCount`, `value.replicatesTest.{f,pValue,...}` (6),
`outliers.<h>.value.{outliersCount,outliersList[]}` (1), `parameters.<NAME>.<h0>.value.dsList[]` (fitted data set indices).
TWO_WAY extras: `anovaTable.matchedFactor*` and `matchingTest` (RM), `randomEffects.{matchedFactor,residual}.{variance,sd}` (REML),
`differenceBetweenRowMeans`/`ColMeans`, `interaction`, `dataSummary`, `means`.

`<h0>` = `d571a627-1d57-538c-9727-83a878cf55f1`, the key that always denotes the empty id `{}`:
scalars are wrapped as `{<h0>: {id:{}, value: X}}`. A parameter is either fitted or constrained;
`status` CONSTANT means a fixed value (SE and CI are `"undefined"`).

Excerpt (4PL, `14204350_0`, trimmed):
```json
{"content":{"models":{"61cd7e7c-ea69-5af6-b42b-8ca824a44ea4":{
  "id":{"col":{"uid":"7774137D-...","title":"276A","idx":0},"model":{"name":"Model 1","title":"Top unconstrained"}},
  "value":{"status":"COMPLETED","iterationCount":10,
   "parameters":{
    "Bottom":{"d571a627-...":{"id":{},"value":{"status":"CONSTANT","estimate":0.0,"se":"undefined","ci":{"lower":"undefined","upper":"undefined","level":95.0}}}},
    "IC50":{"d571a627-...":{"id":{},"value":{"status":"REGULAR","estimate":1.1998428452227864e-06,"se":1.3534475862515756e-07,
            "ci":{"lower":9.415068874247736e-07,"upper":1.5964960472147811e-06,"level":95.0},"dsList":[0]}}}},
   "covariance":{"Top":{"IC50":{"d571a627-...":{"id":{},"value":0.755180378846367}}}},
   "goodnessOfFit":{"df":27.0,"r2":{"d571a627-...":{"id":{},"value":0.9880958462695171}},"adjR2":0.9872,"syx":0.03447,"aicc":-195.6256}}}}}}
```
Observed: an INTERRUPTED fit has only `status`, `modelDescription`, `parameters` (estimates) and `iterationCount`; no `goodnessOfFit`.

### 2.6 AREA_UNDER_CURVE (78 analyses; 73 with `content`, 5 stubs)
`parameters.content` (constant across the corpus): `calc.baseline.{useSpecificValue true, value, firstRowsMeanCount 1, lastRowsMeanCount 0}`,
`calc.peak.height.{definePeakByAmplitudePercentage, minimumAmplitudePercentage 10.0, minimumYUnitCount}`,
`calc.peak.width.{ignoreNarrowPeak false, adjacentPointCount 2}`, `calc.peak.calcPositivePeaksOnly true`,
`output.significantDigitCount 4`.

`results.content`: `status` and `samples` only (73 of 73). AUC has no SE, CI, or p-value.

| value | path |
|---|---|
| per data set | `samples.<h>.id.col.{uid,title,idx}` |
| status | `samples.<h>.value.status` (`VALID`) |
| baseline | `samples.<h>.value.summary.baseline` |
| total area | `samples.<h>.value.summary.totalArea` |
| area of peaks only | `samples.<h>.value.summary.totalPeakArea` |
| number of peaks | `samples.<h>.value.summary.peakCount` |
| per peak | `samples.<h>.value.peaks."Peak N".{firstX,lastX,peakX,peakY,area,areaPercentage}` |

Peak keys are the literal strings `Peak 1`, `Peak 2`, ... (Peak 1 in 73 of 73, Peak 2 in 13, Peak 3 in 11,
Peak 4 in 7, Peak 5 in 1). Degenerate extra peaks (zero width) have `area 0.0` and
`areaPercentage "undefined"` (79 occurrences).
```json
{"content":{"status":{"error":"VALID","warning":[]},"samples":{"89754aa6-1d71-5e65-b0b5-a434ce5fcd1c":{
   "id":{"col":{"uid":"C9CEA7CF-...","title":"DD","idx":1}},
   "value":{"status":"VALID","summary":{"baseline":0.0,"peakCount":1,"totalArea":0.1355,"totalPeakArea":0.1355},
            "peaks":{"Peak 1":{"firstX":0.0,"lastX":0.5,"peakX":0.25,"peakY":0.542,"area":0.1355,"areaPercentage":100.0}}}}}}}
```
`Number of Peaks`, then `Peak N` blocks with one value column per data set.

### 2.7 Other classes
NORMALITY_TESTS, DESCRIPTIVE_STATISTICS, FREQUENCY_DISTRIBUTION (`samples`), INTERPOLATION, SIMPLE_LINEAR_REGRESSION
(`models`), CORRELATION (`pearsonTestModel`), CONTINGENCY_TABLE (`fisherExactTest`), MULTIPLE_TWO_SAMPLE_TESTS (`rows`,
`summary`), SURVIVAL (`curveComparison`, `ratios`); ROW_STATISTICS, TRNSFORM, REMOVE_BASELINE have `status` only.

## 3. Number and status encoding

### 3.1 JSON numbers

- Python `json` is sufficient. `NaN`, `Infinity`, `-Infinity` and bare `null` values do not occur in
  any `results.json` (0 of 549 files).
- Floats keep full double precision (17 significant digits, exponent as `1.2689678155570057e-07`).
  Integral statistics are written as floats (`df: 12.0`, `dfNumerator: 3.0`) and counts as ints
  (`n`, `pointCount`, `comparisonCount`, `letterCount`). Accept both for every numeric field.
- Negative zero occurs (`negativeRanksSum: -0.0`).
- `level` of a p-value is alpha (0.05); `level` of a CI is the percent (95.0).

### 3.2 p-values
A p-value is always an object (never a string, never a bare float):
`{"value": 4.027e-18, "level": 0.05, "isSignificant": true, "state": "P_VALUE_EQUAL"}`.
- `value` is the numeric p (no `<0.0001` strings; that display style is produced by the renderer from
  `output.pValueStyle`). Values down to about 1e-18 occur.
- `state`: `P_VALUE_EQUAL` (1,811 occurrences) means `value` is exact. `P_VALUE_GREATER` (10, all in
  NORMALITY_TESTS) means the true p is greater than `value` (a bound). No other states occur.
- `value` is exactly `1.0` in 29 cases (adjusted p capped at 1) and the string `"undefined"` in 1
  (NLR replicates test); handle with `isinstance(value, (int, float))`.
- `isSignificant` is the verdict at `level`.
- Rank tests carry up to three: `pValue` (reported), `pValueExact`, `pValueApproximate`.
- Multiple comparisons: `pValueAdjusted` and/or `pValueIndividual` (unadjusted; the only one under `No correction`).

### 3.3 Missing and non-computable numbers
- A number that Prism could not compute is the **string `"undefined"`** (same sentinel in
  `parameters.json`), or the key is simply absent. Seen at: NLR `se` (302), `ci.lower` (847),
  `ci.upper` (911), `covariance` cells (1,344), `aicc`, AUC `areaPercentage` (79),
  multiple two-sample tests `level`/`threshold`/`D`/rank sums, SIMPLE_LINEAR_REGRESSION `se`/CI,
  t-test `meanSE` (20). Reader rule: a string in a numeric slot maps to `None`.
- No other numeric strings (`"NaN"`, `"inf"`) exist.
- In `data.csv`, missing = empty string; no `NA`/`NaN` literals were looked for beyond empty cells.

### 3.4 Status and warnings
- `content.status = {"error": <code>, "warning": [<code>...]}` is present in every `content`.
  `error` values seen: `VALID` (all but 3), `INVALID_DATA_SINGLE_COLUMN` (MULTIPLE_TWO_SAMPLE_TESTS),
  `INVALID_DATA_RM_MISSING_SUBJECT_VAL`, `INVALID_DATA_TOO_FEW_COLUMNS` (ONE_WAY_ANOVA). With an
  invalid error the model keys are missing.
- `warning[]` codes seen: `INCOMPLETE_CI` 24, `UNSTABLE_PARAMETERS` 6, `NON_POSITIVE_VALUES` 3,
  `MEAN_VALUES_ANALYZED` 1, `MISSING_VALUES` 1.
- Nested `status` strings: `VALID` 2,315, `REGULAR` 2,326, `COMPLETED` 432, `CONSTANT` 300, `CALCULATED` 68, `TOO_FEW_POINTS` 41,
  `UNSTABLE` 20, `HIT_CONSTRAINT` 12, `PERFECT_FIT` 9, `INVALID`/`SD_ZERO`/`UNKNOWN`/`INTERRUPTED`/`NOT_CONVERGED`-variants < 10 each.
  A numeric field next to any other status than `VALID`/`REGULAR`/`CONSTANT`/`COMPLETED`/`CALCULATED` is usually missing or `"undefined"`.
- Human-readable alerts also live in `analyses/<A>/sheet.json.alertText` and in
  `floating_notes/*.json` (`text.string`, `isAuto true`, e.g. "Bartlett's test cannot be computed because
  at least one column contains only one value repeated"). They are not structured.

### 3.5 Hash keys inside `results.json`
Collections are dicts keyed by UUID-shaped lower-case strings whose version nibble is 5 (e.g.
`61cd7e7c-ea69-5af6-b42b-8ca824a44ea4`). They look like deterministic hashes of the `id` object: the
empty `id` `{}` always maps to `d571a627-1d57-538c-9727-83a878cf55f1`. Do not interpret or
reproduce the key; iterate `.values()` and read `value["id"]`. Dict order is not column order
(e.g. `compactLetterDisplay` is sorted by letter/mean): sort by `id.col.idx` / `id.row.idx`.
`id` shapes: `{}` 10,418; `{col}` 2,376; `{col,model}` 429; `{col,row}` 300; `{row}` 210; a list of
`{col,model}` pairs 72 (model comparison).

### 3.6 `isCalculated` and presence of `results.json`
`analyses/<A>/results.json` exists for 549 of 549 analyses. Semantics of `sheet.json.isCalculated`:

| `isCalculated` | analyses | `results.json` has `content` | rendered result csv non-empty |
|---|---|---|---|
| `true` | 358 | 358 of 358 | 357 (1 has only empty tables) |
| `false` | 69 | 0 of 69 (stub `{"@class"}`) | 21 of 69 (48 have none) |
| key missing | 122 | 65 of 122 (57 stubs) | 122 of 122 |

- `isCalculated` appears with Prism 10.1: 116 of the 122 "missing" analyses are in files last saved by
  10.0.x (`modifiedBy.version`), the other 6 in 10.1/10.2 files. In 10.0-saved files `results.json` is
  incomplete: some classes are stubs although the rendered tables in `data.csv` are complete
  (e.g. NORMALITY_TESTS 30, T_TESTS 18, ONE_WAY 6, TWO_WAY 3). Treat a missing key as "unknown" and
  decide by presence of `content` in `results.json`.
- `isCalculated: false` = analysis defined but not calculated; its result tables, if any, are empty
  shells (heading rows such as `Best-fit values` with blank values).
- Reader rule: `has_results = 'content' in results`; for stubs with non-empty rendered tables the
  fallback is parsing the report csv (display-rounded, layout-dependent).

## 4. Surprises, pitfalls, reader checklist
1. Members are DEFLATE, not stored; directory entries exist in the zip.
2. `document.sheets` is partial (4 analyses, 6 graphs unlisted; 1,055 of 1,742 data sheets are result tables).
3. `sheet.table.uid` (folder under `data/tables/`) differs from the sheet id.
4. `data.csv` is headerless; titles live in `data/sets/<D>.json` (3 title shapes, embedded `\r`).
   `content.json.numberOfColumns` is wrong in 15 tables; use the real width.
5. 84 `view` result tables have no table folder; 45 `data.csv` are 0 bytes.
6. Replicates come as `replicates` (list) or `"replicate ranges"` (key with a space).
7. `"undefined"` string marks non-computable numbers in `results.json` and `parameters.json`.
8. p-values are objects; `P_VALUE_GREATER` marks a bound; no NaN or Infinity; `-0.0` exists.
9. Hash keys are meaningless order; t-test `descriptiveStatistics` uses `sample1`/`sample2`, and `sample1` is the
   second input column under `swapDirection`.
10. CI `level` is 95.0 (percent) except 3 REML CIs with 0.05; p `level` is alpha.
11. `isCalculated` is absent in 10.0.x files; their `results.json` can be a stub while the rendered tables are complete.
12. Applied multiple-comparison method is in the results, not (reliably) in the parameters; names contain non-ASCII.
13. Non-ASCII is common (CJK titles, `Š`, `í`); JSON and CSV are UTF-8 without BOM.
14. Up to 212 MB uncompressed (`media/*.emf|svg`); open members lazily; skip `media/`, `graphs/*/data.bin`, `misc/*.bin`.
15. Opaque binaries: `data.bin` (magic `PCFFGRA4`), `used_fonts.bin` (`PCFF`), `misc/<id>.bin`; `*.dt` is 32 hex chars, not md5.
16. Corpus gaps: Kruskal-Wallis/Friedman, KS results (stubs only), mixed models, three-way ANOVA, global NLR fits,
    Prism 12+. The `$id` schema paths imply per-class schemas inside Prism; none ships in the archive.

Reader outline (stdlib only): `zipfile` -> `document.json` -> enumerate `data/sheets/*/sheet.json` and
`analyses/*/sheet.json` -> resolve tables via `table.uid`, columns via `table.dataSets` -> `csv.reader(io.StringIO(text, newline=''))`
-> load `parameters.json` / `results.json` lazily, normalise p-value objects, `"undefined"` -> `None`, hash dicts -> lists
sorted by `id.col.idx` / `id.row.idx`.
