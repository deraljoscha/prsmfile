#!/usr/bin/env python3
"""Build examples/example.prism, a synthetic file in Prism's format (NOT saved by Prism).

Run it from the repository root:

    uv run --with scipy==1.18.1 --with statsmodels==0.15.0 --with numpy==2.5.5 --with pandas==3.1.1 --with patsy==1.0.3 python scripts/make_example.py

The data are invented lab-style numbers (written out below, drawn once from a seeded random
generator and rounded). Every statistic stored in the file is computed from those numbers.
The dev-only libraries (never runtime dependencies of prsmfile) and what they compute:

  scipy 1.18.1       scipy.stats.ttest_ind(equal_var=False): Welch t, df, p and the confidence
                     interval of the difference; scipy.stats.f: p of the variance-ratio F test;
                     scipy.stats.f_oneway: one-way F and p; scipy.stats.tukey_hsd: Tukey mean
                     differences, adjusted p and confidence intervals; scipy.stats.levene
                     (center="median", the Brown-Forsythe test) and scipy.stats.bartlett;
                     scipy.stats.shapiro: Shapiro-Wilk W and p; scipy.stats.t: p and critical
                     values of the Sidak-adjusted two-way comparisons;
                     scipy.stats.studentized_range: cross-check of the Tukey p-values.
  statsmodels 0.15.0 (with pandas) ols + anova_lm (type II, the design is balanced): two-way ANOVA sums of
                     squares, degrees of freedom, F and p.
  numpy              means, SD, SEM, medians, sums of squares, numpy.trapezoid for the area
                     under the curve.

Everything else (mean squares, percent of total, R squared, standard errors, q) is plain
arithmetic on those numbers. The script asserts that independent routes agree (f_oneway against
the ANOVA table, Tukey p against the studentized range, statsmodels against the table).

The file is deterministic: running the script twice gives byte-identical output, provided the
pinned versions above are used (other versions may round the last digits differently).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import scipy
import statsmodels
import statsmodels.api as sm
from scipy import stats
from statsmodels.formula.api import ols

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.builder import PrismBuilder  # noqa: E402  (dev helper, not part of the package)

OUT = ROOT / "examples" / "example.prism"
OK = {"error": "VALID", "warning": []}
ALPHA = 0.05
SIDAK = "Bonferroni-Šídák"

# ---- invented data -----------------------------------------------------------------------

LYSO_CONTROL = [41.5, 48.2, 45.9, 42.9, 36.3, 34.3]
LYSO_HEAT = [58.1, 55.9, 39.0, 54.8, 36.7, 57.0]

MASS = {
    "Control": [125.0, 127.7, 113.6, 124.9, 115.4, 103.9],
    "Nitrogen low": [140.6, 139.7, 136.1, 137.1, 126.7, 134.1],
    "Nitrogen high": [166.5, 157.1, 158.7, 170.1, 142.1, 168.4],
}

ROOTS = {  # row (genotype) -> column (light) -> four replicates
    "Wild type": {"Low light": [7.0, 7.1, 6.5, 6.5], "Medium light": [7.9, 8.3, 7.8, 8.7],
                  "High light": [9.1, 8.4, 8.6, 8.9]},
    "Mutant": {"Low light": [6.6, 4.8, 6.5, 5.8], "Medium light": [6.3, 6.9, 8.0, 6.8],
               "High light": [6.9, 7.0, 6.7, 7.4]},
}

TIME = [0.0, 2.0, 5.0, 10.0, 15.0, 20.0, 30.0, 45.0, 60.0]
TRACER = [66.5, 58.6, 49.3, 37.2, 25.5, 19.6, 10.6, 7.0, 4.0]

# ---- helpers -----------------------------------------------------------------------------


def f(x) -> float:
    return float(x)


def pobj(p: float) -> dict:
    p = f(min(max(p, 0.0), 1.0))
    return {"value": p, "level": ALPHA, "isSignificant": bool(p < ALPHA), "state": "P_VALUE_EQUAL"}


def col(uid: str, idx: int, title: str) -> dict:
    return {"col": {"uid": uid, "title": title, "idx": idx}}


def fmt(x, digits=4) -> str:
    """Prism-like rendering with four significant digits."""
    if x == 0:
        return "0.000"
    text = f"{x:.{digits}g}"
    if "e" in text:
        text = f"{x:.{digits}f}"
    return text


def pfmt(p: float) -> str:
    return "<0.0001" if p < 0.0001 else f"{p:.4f}"


def stars(p: float) -> str:
    return "****" if p < 0.0001 else "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "ns"


def desc(x) -> dict:
    a = np.asarray(x, dtype=float)
    return {"n": int(a.size), "mean": f(a.mean()), "sd": f(a.std(ddof=1)),
            "meanSE": f(a.std(ddof=1) / np.sqrt(a.size)), "minimum": f(a.min()),
            "median": f(np.median(a)), "maximum": f(a.max())}


def cells(rows):
    return [[str(c) for c in r] for r in rows]


def column_rows(columns):
    n = max(len(v) for v in columns)
    return [[str(v[i]) if i < len(v) else "" for v in columns] for i in range(n)]


KEY = {}  # key statistics, printed at the end and checked by tests/test_examples.py

# ---- 1. Welch t test ---------------------------------------------------------------------


def add_welch(b: PrismBuilder) -> None:
    a, h = np.array(LYSO_CONTROL), np.array(LYSO_HEAT)
    sid = b.add_raw_table(
        "Lysozyme activity", "column",
        [("Control", "y_single", 1), ("Heat treated", "y_single", 1)],
        column_rows([LYSO_CONTROL, LYSO_HEAT]))
    ua, ub = b.data_sets(sid)
    res = stats.ttest_ind(h, a, equal_var=False)  # B minus A, as Prism reports it
    ci = res.confidence_interval(0.95)
    diff = f(h.mean() - a.mean())
    se = f(np.sqrt(a.var(ddof=1) / a.size + h.var(ddof=1) / h.size))
    assert abs(diff / se - res.statistic) < 1e-9
    r2 = f(res.statistic ** 2 / (res.statistic ** 2 + res.df))
    va, vh = a.var(ddof=1), h.var(ddof=1)
    big, small, nb, ns = (vh, va, h.size, a.size) if vh >= va else (va, vh, a.size, h.size)
    fvar = f(big / small)
    pvar = f(min(1.0, 2 * stats.f.sf(fvar, nb - 1, ns - 1)))
    KEY["welch"] = {"t": f(res.statistic), "df": f(res.df), "p": f(res.pvalue), "diff": diff,
                    "ci_lower": f(ci.low), "ci_upper": f(ci.high), "n": 6}
    results = {
        "status": OK,
        "welchTTestModel": {
            "status": "VALID",
            "welchTTest": {"status": "VALID", "t": f(res.statistic), "df": f(res.df),
                           "pValue": pobj(res.pvalue)},
            "differenceOfMeans": {
                "n1": int(a.size), "mean1": f(a.mean()), "n2": int(h.size), "mean2": f(h.mean()),
                "difference": diff, "stdErrorOfDifference": se,
                "confidenceIntervalOfDifference": {"lower": f(ci.low), "upper": f(ci.high), "level": 95.0},
                "rSquared": r2},
            "varianceTest": {"status": "VALID", "f": fvar, "dfNumerator": float(nb - 1),
                             "dfDenominator": float(ns - 1), "pValue": pobj(pvar)},
        },
        "descriptiveStatistics": {  # sample1 is the second input column, as Prism stores it
            "sample1": {"id": col(ub, 1, "Heat treated"), "value": desc(h)},
            "sample2": {"id": col(ua, 0, "Control"), "value": desc(a)},
        },
    }
    params = {"experimentalDesign": "WELCH_T_TEST",
              "options": {"pValueTailType": "P_VALUE_TWO_TAILED", "swapDirection": True}}
    view = [
        ["Table Analyzed", "Lysozyme activity"], ["", ""],
        ["Column B", "Heat treated"], ["vs.", "vs."], ["Column A", "Control"], ["", ""],
        ["Unpaired t test with Welch's correction", ""],
        ["    P value", pfmt(res.pvalue)], ["    P value summary", stars(res.pvalue)],
        [f"    Significantly different (P < {ALPHA})?", "Yes" if res.pvalue < ALPHA else "No"],
        ["    One- or two-tailed P value?", "Two-tailed"],
        ["    Welch-corrected  t, df", f"t={fmt(res.statistic)}, df={fmt(res.df)}"], ["", ""],
        ["How big is the difference?", ""],
        ["    Mean of column A", fmt(a.mean())], ["    Mean of column B", fmt(h.mean())],
        ["    Difference between means (B - A) ± SEM", f"{fmt(diff)} ± {fmt(se)}"],
        ["    95% confidence interval", f"{fmt(ci.low)} to {fmt(ci.high)}"],
        ["    R squared (eta squared)", fmt(r2)], ["", ""],
        ["F test to compare variances", ""],
        ["    F, DFn, Dfd", f"{fmt(fvar)}, {nb - 1}, {ns - 1}"], ["    P value", pfmt(pvar)],
        ["    P value summary", stars(pvar)],
        [f"    Significantly different (P < {ALPHA})?", "Yes" if pvar < ALPHA else "No"], ["", ""],
        ["Data analyzed", ""], ["    Sample size, column A", str(a.size)],
        ["    Sample size, column B", str(h.size)],
    ]
    b.add_analysis("Welch's t test of Lysozyme activity", "T_TESTS_AND_NONPARAMETRIC", params, results,
                   inputs=(("A", "Control", (sid, 0)), ("B", "Heat treated", (sid, 1))),
                   views=(("Tabular results", view, "text", 2),))


# ---- 2. One-way ANOVA with Tukey, and a Shapiro-Wilk analysis (generic reader) ------------


def add_oneway(b: PrismBuilder) -> None:
    names = list(MASS)
    groups = [np.array(MASS[k]) for k in names]
    sid = b.add_raw_table("Shoot dry mass", "column", [(k, "y_single", 1) for k in names],
                          column_rows([MASS[k] for k in names]))
    uids = b.data_sets(sid)
    k, n_all = len(groups), sum(g.size for g in groups)
    grand = np.concatenate(groups).mean()
    ss_b = f(sum(g.size * (g.mean() - grand) ** 2 for g in groups))
    ss_w = f(sum(((g - g.mean()) ** 2).sum() for g in groups))
    df_b, df_w = k - 1, n_all - k
    ms_b, ms_w = ss_b / df_b, ss_w / df_w
    fval = ms_b / ms_w
    fo = stats.f_oneway(*groups)
    assert abs(fo.statistic - fval) < 1e-9 * max(1.0, fval)
    p_f = f(stats.f.sf(fval, df_b, df_w))
    assert abs(p_f - fo.pvalue) < 1e-12 * max(1.0, p_f) + 1e-300
    bf = stats.levene(*groups, center="median")
    bt = stats.bartlett(*groups)
    tk = stats.tukey_hsd(*groups)
    tci = tk.confidence_interval(0.95)
    pairs = []
    for i in range(k):
        for j in range(i + 1, k):
            d = f(tk.statistic[i][j])
            assert abs(d - (groups[i].mean() - groups[j].mean())) < 1e-9
            se = f(np.sqrt(ms_w * (1 / groups[i].size + 1 / groups[j].size)))
            q = f(abs(d) * np.sqrt(2) / se)
            p_adj = f(tk.pvalue[i][j])
            assert abs(stats.studentized_range.sf(q, k, df_w) - p_adj) < 1e-6
            pairs.append((i, j, d, se, q, p_adj, f(tci.low[i][j]), f(tci.high[i][j])))
    KEY["oneway"] = {"f": fval, "p": p_f, "df_between": df_b, "df_within": df_w, "ss_between": ss_b,
                     "ss_within": ss_w,
                     "tukey": {f"{names[i]} vs {names[j]}": {"diff": d, "p_adj": pa}
                               for i, j, d, _se, _q, pa, _l, _h in pairs}}
    tests: dict = {}
    for i in range(k):
        inner = [(col(uids[j], j, names[j]),
                  {"status": "VALID", "meansDifference": d, "meansDifferenceSE": se,
                   "meansDifferenceCI": {"lower": lo, "upper": hi, "level": 95.0},
                   "statistic": q, "df": float(df_w), "pValueAdjusted": pobj(p_adj),
                   "sample1": {"value": {"mean": f(groups[i].mean()), "n": int(groups[i].size)}},
                   "sample2": {"value": {"mean": f(groups[j].mean()), "n": int(groups[j].size)}}})
                 for (a, j, d, se, q, p_adj, lo, hi) in pairs if a == i]
        if inner:
            tests[i] = (col(uids[i], i, names[i]), PrismBuilder.keyed(inner))
    model = {
        "status": "VALID",
        "anovaTable": {
            "colFactor": {"ss": ss_b, "df": float(df_b), "ms": ms_b, "r2": ss_b / (ss_b + ss_w),
                          "fTest": {"status": "VALID", "f": fval, "dfNumerator": float(df_b),
                                    "dfDenominator": float(df_w), "pValue": pobj(p_f)}},
            "residual": {"ss": ss_w, "df": float(df_w), "ms": ms_w},
            "total": {"ss": ss_b + ss_w, "df": float(n_all - 1)}},
        "brownForsytheTest": {"status": "VALID", "f": f(bf.statistic), "dfNumerator": float(k - 1),
                              "dfDenominator": float(n_all - k), "pValue": pobj(bf.pvalue)},
        "bartlettTest": {"status": "VALID", "statistic": f(bt.statistic), "pValue": pobj(bt.pvalue)},
        "multipleComparisons": {
            "status": "VALID", "method": "Tukey", "comparisonCount": len(pairs),
            "significantCount": sum(1 for p in pairs if p[5] < ALPHA),
            "tests": PrismBuilder.keyed(tests.values())},
        "dataSummary": {"levelCount": k, "pointCount": n_all},
    }
    results = {
        "status": OK, "ordinaryAnovaModel": model,
        "descriptiveStatistics": PrismBuilder.keyed(
            [(col(uids[i], i, names[i]), desc(groups[i])) for i in range(k)]),
    }
    params = {"experimentalDesign": "ORDINARY_ANOVA",
              "postTests": {"type": "PAIRWISE_TESTS",
                            "pairwiseTests": {"pairwiseDesign": {"type": "ALL_VS_ALL"}}}}
    anova_view = [
        ["Table Analyzed", "Shoot dry mass", "", "", "", ""], ["", "", "", "", "", ""],
        ["ANOVA summary", "", "", "", "", ""], ["  F", fmt(fval), "", "", "", ""],
        ["  P value", pfmt(p_f), "", "", "", ""], ["  P value summary", stars(p_f), "", "", "", ""],
        [f"  Significant diff. among means (P < {ALPHA})?", "Yes" if p_f < ALPHA else "No", "", "", "", ""],
        ["  R squared", fmt(ss_b / (ss_b + ss_w)), "", "", "", ""], ["", "", "", "", "", ""],
        ["Brown-Forsythe test", "", "", "", "", ""],
        ["  F (DFn, DFd)", f"{fmt(bf.statistic)} ({k - 1}, {n_all - k})", "", "", "", ""],
        ["  P value", pfmt(bf.pvalue), "", "", "", ""], ["", "", "", "", "", ""],
        ["ANOVA table", "SS", "DF", "MS", "F (DFn, DFd)", "P value"],
        ["  Treatment (between columns)", fmt(ss_b), str(df_b), fmt(ms_b),
         f"F ({df_b}, {df_w}) = {fmt(fval)}", "P<0.0001" if p_f < 0.0001 else f"P={p_f:.4f}"],
        ["  Residual (within columns)", fmt(ss_w), str(df_w), fmt(ms_w), "", ""],
        ["  Total", fmt(ss_b + ss_w), str(n_all - 1), "", "", ""], ["", "", "", "", "", ""],
        ["Data summary", "", "", "", "", ""], ["  Number of treatments (columns)", str(k), "", "", "", ""],
        ["  Number of values (total)", str(n_all), "", "", "", ""],
    ]
    mc_view = [["Number of families", "1", "", "", "", ""],
               ["Number of comparisons per family", str(len(pairs)), "", "", "", ""],
               ["Alpha", str(ALPHA), "", "", "", ""], ["", "", "", "", "", ""],
               ["Tukey's multiple comparisons test", "Mean Diff.", "95.00% CI of diff.",
                "Below threshold?", "Summary", "Adjusted P Value"]]
    for i, j, d, _se, _q, pa, lo, hi in pairs:
        mc_view.append([f"  {names[i]} vs. {names[j]}", fmt(d), f"{fmt(lo)} to {fmt(hi)}",
                        "Yes" if pa < ALPHA else "No", stars(pa), pfmt(pa)])
    inputs = tuple((chr(65 + i), names[i], (sid, i)) for i in range(k))
    b.add_analysis("Ordinary one-way ANOVA of Shoot dry mass", "ONE_WAY_ANOVA", params, results,
                   inputs=inputs,
                   views=(("ANOVA results", anova_view, "text", 6), ("Multiple comparisons", mc_view, "text", 6)))

    # Shapiro-Wilk on every group: a class without a dedicated reader (generic values)
    samples = []
    for i in range(k):
        w = stats.shapiro(groups[i])
        samples.append((col(uids[i], i, names[i]), {
            "normalityModel": {
                "status": "VALID",
                "dAgostinoPearsonTest": {"status": "TOO_FEW_POINTS"},
                "andersonDarlingTest": {"status": "TOO_FEW_POINTS"},
                "shapiroWilkTest": {"status": "VALID", "W": f(w.statistic), "pValue": pobj(w.pvalue)},
                "allTestsPassed": bool(w.pvalue >= ALPHA),
                "descriptiveStatistics": {"n": int(groups[i].size), "mean": f(groups[i].mean()),
                                          "sd": f(groups[i].std(ddof=1))}},
            "dataSummary": {"valueCount": int(groups[i].size)}}))
        KEY.setdefault("shapiro", {})[names[i]] = {"W": f(w.statistic), "p": f(w.pvalue)}
    nparams = {"data": {"handleReplicatesAs": "AVERAGE"},
               "calc": {"testforNormality": True, "testforLognormality": False},
               "options": {"significanceLevel": ALPHA},
               "output": {"significantDigitCount": 4}}
    b.add_analysis("Normality and Lognormality Tests of Shoot dry mass", "NORMALITY_TESTS", nparams,
                   {"status": OK, "samples": PrismBuilder.keyed(samples)}, inputs=inputs)


# ---- 3. Two-way ANOVA with Sidak comparisons ----------------------------------------------


def add_twoway(b: PrismBuilder) -> None:
    rows, cols = list(ROOTS), list(next(iter(ROOTS.values())))
    sid = b.add_raw_table(
        "Root length", "grouped", [(c, "y_replicates", 4) for c in cols],
        [[r] + [str(v) for c in cols for v in ROOTS[r][c]] for r in rows], row_titles=True)
    uids = b.data_sets(sid)
    long = pd.DataFrame([{"genotype": r, "light": c, "y": v}
                         for r in rows for c in cols for v in ROOTS[r][c]])
    model = ols("y ~ C(genotype) * C(light)", data=long).fit()
    tab = sm.stats.anova_lm(model, typ=2)
    ss = {"rowFactor": f(tab.loc["C(genotype)", "sum_sq"]), "colFactor": f(tab.loc["C(light)", "sum_sq"]),
          "rowFactorVsColFactor": f(tab.loc["C(genotype):C(light)", "sum_sq"]),
          "residual": f(tab.loc["Residual", "sum_sq"])}
    dfs = {"rowFactor": 1, "colFactor": 2, "rowFactorVsColFactor": 2, "residual": 18}
    assert [int(tab.loc[i, "df"]) for i in ("C(genotype)", "C(light)", "C(genotype):C(light)", "Residual")] == \
        [dfs["rowFactor"], dfs["colFactor"], dfs["rowFactorVsColFactor"], dfs["residual"]]
    total = sum(ss.values())
    ms_w = ss["residual"] / dfs["residual"]
    anova = {}
    ftests = {}
    for key, sm_name in (("rowFactor", "C(genotype)"), ("colFactor", "C(light)"),
                         ("rowFactorVsColFactor", "C(genotype):C(light)")):
        ms = ss[key] / dfs[key]
        fv = ms / ms_w
        assert abs(fv - tab.loc[sm_name, "F"]) < 1e-9 * max(1.0, fv)
        p = f(stats.f.sf(fv, dfs[key], dfs["residual"]))
        assert abs(p - tab.loc[sm_name, "PR(>F)"]) < 1e-12 * max(1.0, p) + 1e-300
        ftests[key] = (fv, p)
        anova[key] = {"ss": ss[key], "df": float(dfs[key]), "ms": ms, "variation": ss[key] / total * 100,
                      "fTest": {"status": "VALID", "f": fv, "dfNumerator": float(dfs[key]),
                                "dfDenominator": float(dfs["residual"]), "pValue": pobj(p)}}
    anova["residual"] = {"ss": ss["residual"], "df": float(dfs["residual"]), "ms": ms_w,
                         "variation": ss["residual"] / total * 100}
    anova["total"] = {"ss": total, "df": float(len(long) - 1)}
    # Sidak comparisons of the column means within each row, one family of six
    m = len(rows) * len(cols) * (len(cols) - 1) // 2
    alpha_adj = 1 - (1 - ALPHA) ** (1 / m)
    tcrit = f(stats.t.ppf(1 - alpha_adj / 2, dfs["residual"]))
    tests = []
    comp_view = []
    for ri, r in enumerate(rows):
        for i in range(len(cols)):
            inner = []
            for j in range(i + 1, len(cols)):
                a, c = np.array(ROOTS[r][cols[i]]), np.array(ROOTS[r][cols[j]])
                d = f(a.mean() - c.mean())
                se = f(np.sqrt(ms_w * (1 / a.size + 1 / c.size)))
                t = d / se
                p_ind = f(2 * stats.t.sf(abs(t), dfs["residual"]))
                p_adj = f(1 - (1 - p_ind) ** m)
                cid1 = {"row": {"idx": ri, "title": r}, "col": {"uid": uids[i], "title": cols[i], "idx": i}}
                cid2 = {"row": {"idx": ri, "title": r}, "col": {"uid": uids[j], "title": cols[j], "idx": j}}
                inner.append((cid2, {
                    "status": "VALID", "meansDifference": d, "meansDifferenceSE": se,
                    "meansDifferenceCI": {"lower": d - tcrit * se, "upper": d + tcrit * se, "level": 95.0},
                    "statistic": abs(t), "df": float(dfs["residual"]), "pValueAdjusted": pobj(p_adj),
                    "sample1": {"value": {"mean": f(a.mean()), "n": int(a.size)}},
                    "sample2": {"value": {"mean": f(c.mean()), "n": int(c.size)}}}))
                comp_view.append((r, cols[i], cols[j], d, d - tcrit * se, d + tcrit * se, p_adj))
                KEY.setdefault("twoway_sidak", {})[f"{r}: {cols[i]} vs {cols[j]}"] = {"diff": d, "p_adj": p_adj}
            if inner:
                tests.append(({"row": {"idx": ri, "title": r},
                               "col": {"uid": uids[i], "title": cols[i], "idx": i}},
                              PrismBuilder.keyed(inner)))
    KEY["twoway"] = {k: {"f": v[0], "p": v[1], "ss": ss[k], "df": dfs[k]} for k, v in ftests.items()}
    KEY["twoway"]["residual"] = {"ss": ss["residual"], "df": dfs["residual"]}
    results = {
        "status": OK,
        "ordinaryAnovaModel": {
            "status": "VALID",
            "factorNames": {"rowFactor": "Genotype", "colFactor": "Light"},
            "anovaTable": anova,
            "multipleComparisons": {"status": "VALID", "method": SIDAK, "familyCount": 1,
                                    "comparisonPerFamilyCount": m, "tests": PrismBuilder.keyed(tests)},
            "dataSummary": {"rowCount": len(rows), "colCount": len(cols), "pointCount": len(long),
                            "isBalancedDesign": True}},
    }
    params = {"experimentalDesign": "ORDINARY_ANOVA",
              "repeatedMeasures": {"method": "OPTIONAL", "assumeSphericity": False},
              "postTests": {"type": "PAIRWISE_TESTS", "pairwiseTests": {
                  "meansDesignType": "COMPARE_CELLS_BY_COLUMNS_WITHIN_ROWS_SINGLE_FAMILY"}}}

    def prow(label, key):
        fv, p = ftests[key]
        return [f"    {label}", fmt(ss[key]), str(dfs[key]), fmt(ss[key] / dfs[key]),
                f"F ({dfs[key]}, {dfs['residual']}) = {fmt(fv)}", "P<0.0001" if p < 0.0001 else f"P={p:.4f}"]

    view = [
        ["Table Analyzed", "Root length", "", "", "", ""], ["", "", "", "", "", ""],
        ["Two-way ANOVA", "Ordinary", "", "", "", ""], ["    Alpha", str(ALPHA), "", "", "", ""],
        ["", "", "", "", "", ""],
        ["Source of Variation", "% of total variation", "P value", "P value summary", "Significant?", ""],
        *[[f"    {lab}", fmt(ss[k] / total * 100), pfmt(ftests[k][1]), stars(ftests[k][1]),
           "Yes" if ftests[k][1] < ALPHA else "No", ""]
          for lab, k in (("Interaction", "rowFactorVsColFactor"), ("Row Factor", "rowFactor"),
                         ("Column Factor", "colFactor"))],
        ["", "", "", "", "", ""],
        ["ANOVA table", "SS", "DF", "MS", "F (DFn, DFd)", "P value"],
        prow("Interaction", "rowFactorVsColFactor"), prow("Row Factor", "rowFactor"),
        prow("Column Factor", "colFactor"),
        ["    Residual", fmt(ss["residual"]), str(dfs["residual"]), fmt(ms_w), "", ""],
        ["", "", "", "", "", ""],
        ["Data summary", "", "", "", "", ""],
        ["    Number of columns (Column Factor)", str(len(cols)), "", "", "", ""],
        ["    Number of rows (Row Factor)", str(len(rows)), "", "", "", ""],
        ["    Number of values", str(len(long)), "", "", "", ""],
    ]
    b.add_analysis("Ordinary two-way ANOVA of Root length", "TWO_WAY_ANOVA", params, results,
                   inputs=tuple((chr(65 + i), cols[i], (sid, i)) for i in range(len(cols))),
                   views=(("ANOVA results", view, "text", 6),))


# ---- 4. Area under the curve --------------------------------------------------------------


def add_auc(b: PrismBuilder) -> None:
    x, y = np.array(TIME), np.array(TRACER)
    sid = b.add_raw_table("Tracer clearance", "xy", [("Plasma tracer", "y_single", 1)],
                          [[str(a), str(c)] for a, c in zip(TIME, TRACER)],
                          x_data_set=("Time (min)", "y_single", 1))
    (uid,) = b.data_sets(sid)
    area = f(np.trapezoid(y, x))
    peak_i = int(np.argmax(y))
    KEY["auc"] = {"area": area, "peak_x": f(x[peak_i]), "peak_y": f(y[peak_i])}
    results = {"status": OK, "samples": PrismBuilder.keyed([(col(uid, 0, "Plasma tracer"), {
        "status": "VALID",
        "summary": {"baseline": 0.0, "peakCount": 1, "totalArea": area, "totalPeakArea": area},
        "peaks": {"Peak 1": {"firstX": f(x[0]), "lastX": f(x[-1]), "peakX": f(x[peak_i]),
                             "peakY": f(y[peak_i]), "area": area, "areaPercentage": 100.0}}})])}
    params = {"calc": {"baseline": {"useSpecificValue": True, "value": 0.0, "firstRowsMeanCount": 1,
                                    "lastRowsMeanCount": 0},
                       "peak": {"height": {"definePeakByAmplitudePercentage": True,
                                           "minimumAmplitudePercentage": 10.0},
                                "width": {"ignoreNarrowPeak": False, "adjacentPointCount": 2},
                                "calcPositivePeaksOnly": True}},
              "output": {"significantDigitCount": 4}}
    view = [["Baseline", "0"], ["", ""], ["Total Area", fmt(area)], ["Total Peak Area", fmt(area)],
            ["Number of Peaks", "1"], ["", ""], ["Peak 1", ""], ["  First X", fmt(x[0])],
            ["  Last X", fmt(x[-1])], ["  Peak X", fmt(x[peak_i])], ["  Peak Y", fmt(y[peak_i])],
            ["  Area", fmt(area)], ["  %Area", "100.0"]]
    b.add_analysis("Area under the curve of Tracer clearance", "AREA_UNDER_CURVE", params, results,
                   inputs=(("A", "Plasma tracer", (sid, 0)),),
                   views=(("Area under curve", view, "text", 2),))


def main() -> int:
    b = PrismBuilder()
    add_welch(b)
    add_oneway(b)
    add_twoway(b)
    add_auc(b)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    b.save(OUT, user="prsmfile-example")
    print(f"wrote {OUT.relative_to(ROOT)} (scipy {scipy.__version__}, statsmodels {statsmodels.__version__},"
          f" numpy {np.__version__})")
    import json
    print(json.dumps(KEY, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
