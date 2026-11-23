import prsmfile
from prsmfile import PValue, read_analysis
from tests.builder import PrismBuilder
from tests.helpers import assert_sections_well_formed

CLS = "TWO_WAY_ANOVA"
OK = {"error": "VALID", "warning": []}
ORD, GLM, REML = "ordinaryAnovaModel", "repeatedMeasuresGlmAnovaModel", "repeatedMeasuresRemlAnovaModel"


def pobj(v, sig=True):
    return {"value": v, "level": 0.05, "isSignificant": sig, "state": "P_VALUE_EQUAL"}


def pv(v, sig=True):
    return PValue(value=v, alpha=0.05, significant=sig, bound=False)


def cellid(ridx, rtitle, cidx, ctitle):
    row = {"idx": ridx}
    if rtitle is not None:
        row["title"] = rtitle
    col = {"uid": f"U{cidx}", "idx": cidx}
    if ctitle is not None:
        col["title"] = ctitle
    return {"row": row, "col": col}


def run(tmp_path, results, params=None):
    params = {"experimentalDesign": "ORDINARY_ANOVA",
              "repeatedMeasures": {"method": "OPTIONAL", "assumeSphericity": False},
              "postTests": {"type": "PAIRWISE_TESTS",
                            "pairwiseTests": {"meansDesignType": "COMPARE_CELLS_BY_COLUMNS_WITHIN_ROWS_SINGLE_FAMILY"}},
              **(params or {})}
    b = PrismBuilder()
    b.add_analysis("W", CLS, params, results, inputs=(("A", "WT"), ("B", "KO")))
    with prsmfile.open(b.save(tmp_path / "w.prism")) as pf:
        r = read_analysis(pf, pf.analyses()[0])
    assert_sections_well_formed(r)
    return r


def sec(r, title):
    (s,) = [s for s in r.sections if s.title == title]
    return s


def titles(r):
    return [s.title for s in r.sections]


def node(ss, df, ms, variation=None, f=None, p=0.01):
    n = {"ss": ss, "df": df, "ms": ms}
    if variation is not None:
        n["variation"] = variation
    if f is not None:
        n["fTest"] = {"status": "VALID", "f": f, "dfNumerator": 1.0, "dfDenominator": 6.0, "pValue": pobj(p)}
    return n


def res(model, key=ORD, **extra):
    m = {"status": "VALID", **model}
    m.update(extra)
    return {"status": OK, key: m}


UNC = " (uncorrected)"
BY_ROWS = "COMPARE_CELLS_BY_ROWS_WITHIN_COLUMNS_SEPARATE_FAMILIES"
BY_COLS = "COMPARE_CELLS_BY_COLUMNS_WITHIN_ROWS_SINGLE_FAMILY"
SPH = {"method": "REML", "assumeSphericity": True}
NOSPH = {"method": "REML", "assumeSphericity": False}


def rm_params(rm, design=BY_COLS):
    return {"experimentalDesign": "REPEATED_MEASURES_BY_ROWS", "repeatedMeasures": rm,
            "postTests": {"type": "PAIRWISE_TESTS", "pairwiseTests": {"meansDesignType": design}}}


def marked(section):
    return [c for c in section.columns if c.endswith(UNC)]


def mc_model():
    return {"method": "TUKEY", "tests": {}}


def reml_with_mc(variance=0.64):
    m = reml_model()
    m["randomEffects"]["matchedFactor"]["variance"] = variance
    t = {"value": {"meansDifference": 1.0, "meansDifferenceSE": 0.1, "statistic": 2.0, "df": 5.0,
                   "pValueAdjusted": pobj(0.04), "sample1": {"value": {"mean": 3.0, "n": 4}},
                   "sample2": {"value": {"mean": 2.0, "n": 4}},
                   "meansDifferenceCI": {"lower": 0.1, "upper": 1.9, "level": 95.0}}}
    m["multipleComparisons"] = {"method": "TUKEY", "tests": {"a": {"value": {"b": t}}}}
    return m


def glm_model():
    return {"anovaTable": {"rowFactor": node(1, 1, 1, 5.0, 2.0), "matchedFactor": node(9, 3, 3.0)}}


def test_ordinary_never_marked_or_warned(tmp_path):
    r = run(tmp_path, res({"anovaTable": {"rowFactor": node(1, 1, 1, 5.0, 2.0)}}))
    assert r.warnings == [] and marked(sec(r, "ANOVA")) == []


GLM_WARNING = ("Sphericity not assumed: stored values are Geisser-Greenhouse corrected and matched Prism "
               "in the test corpus, but one cross-check with Prism 11.2 found a differing row "
               "(DFn, DFd, P). Compare with Prism if these values matter.")


def test_glm_sphericity_off_has_no_marks_but_warns(tmp_path):
    m = glm_model()
    m["multipleComparisons"] = reml_with_mc()["multipleComparisons"]
    r = run(tmp_path, res(m, GLM), rm_params({"method": "OPTIONAL", "assumeSphericity": False}, BY_ROWS))
    assert marked(sec(r, "ANOVA")) == []
    assert marked(sec(r, "Multiple comparisons (TUKEY)")) == []
    assert r.warnings == [GLM_WARNING]


def test_reml_sphericity_off_by_rows_marks_fixed_and_comparisons(tmp_path):
    r = run(tmp_path, res(reml_with_mc(), REML), rm_params(NOSPH, BY_ROWS))
    assert marked(sec(r, "Fixed effects")) == ["DFn" + UNC, "DFd" + UNC, "P" + UNC]
    c = sec(r, "Multiple comparisons (TUKEY)")
    assert marked(c) == [x + UNC for x in ("Mean diff", "SE", "CI lower", "CI upper", "Statistic", "P adjusted", "P individual")]
    assert "Mean 1" in c.columns and "n 1" in c.columns and "CI level" in c.columns and "df" in c.columns
    assert c.rows[0][c.columns.index("Mean diff" + UNC)] == 1.0
    assert len(r.warnings) == 1 and "multiple comparisons" in r.warnings[0]
    assert "confidence interval of the difference between column means" in r.warnings[0]
    assert "Matching" in titles(r)


def test_reml_sphericity_off_by_columns_marks_fixed_only(tmp_path):
    r = run(tmp_path, res(reml_with_mc(), REML), rm_params(NOSPH, BY_COLS))
    assert marked(sec(r, "Fixed effects")) == ["DFn" + UNC, "DFd" + UNC, "P" + UNC]
    assert marked(sec(r, "Multiple comparisons (TUKEY)")) == []
    assert "recomputes" not in r.warnings[0]


def test_reml_zero_subject_variance_marks_dfd_p(tmp_path):
    r = run(tmp_path, res(reml_with_mc(0), REML), rm_params(SPH, BY_ROWS))
    f = sec(r, "Fixed effects")
    assert marked(f) == ["DFd" + UNC, "P" + UNC] and "DFn" in f.columns and "F" in f.columns
    assert marked(sec(r, "Multiple comparisons (TUKEY)")) == []
    assert "Matching" in titles(r)
    assert len(r.warnings) == 1 and r.warnings[0].startswith("Subject variance is 0")


def test_zero_variance_must_be_number(tmp_path):
    for v in (None, False, "0"):
        r = run(tmp_path, res(reml_with_mc(v), REML), rm_params(SPH))
        assert marked(sec(r, "Fixed effects")) == [] and r.warnings == []


def test_sphericity_missing_or_non_bool_is_not_flagged(tmp_path):
    for rm in ({"method": "REML"}, {"method": "REML", "assumeSphericity": "false"},
               {"method": "REML", "assumeSphericity": None}):
        r = run(tmp_path, res(reml_with_mc(), REML), rm_params(rm, BY_ROWS))
        assert r.warnings == [] and marked(sec(r, "Fixed effects")) == []


def test_sphericity_on_and_variance_positive_has_no_marks(tmp_path):
    g = run(tmp_path, res(glm_model(), GLM), rm_params({"method": "OPTIONAL", "assumeSphericity": True}))
    assert g.warnings == [] and marked(sec(g, "ANOVA")) == []
    r = run(tmp_path, res(reml_with_mc(), REML), rm_params(SPH, BY_ROWS))
    assert r.warnings == []
    assert marked(sec(r, "Fixed effects")) == [] and marked(sec(r, "Multiple comparisons (TUKEY)")) == []


def test_both_situations_union_without_duplicate_suffix(tmp_path):
    r = run(tmp_path, res(reml_with_mc(0), REML), rm_params(NOSPH, BY_ROWS))
    f = sec(r, "Fixed effects")
    assert f.columns == ["Source", "F", "DFn" + UNC, "DFd" + UNC, "P" + UNC]
    assert len(r.warnings) == 2
    assert r.warnings[0].startswith("Sphericity not assumed")
    assert r.warnings[1].startswith("Subject variance is 0")
    assert all(UNC + UNC not in c for sct in r.sections for c in sct.columns)
    assert not any(ch in w for w in r.warnings for ch in "\u2013\u2014")


def test_ordinary_rows_order(tmp_path):
    table = {"rowFactor": node(1, 1, 1, 10.0, 5.0), "colFactor": node(2, 2, 1, 20.0, 6.0),
             "rowFactorVsColFactor": node(3, 2, 1.5, 30.0, 7.0), "residual": node(4, 12, 0.3, 40.0)}
    r = run(tmp_path, res({"anovaTable": table}))
    assert r.kind == "structured" and r.warnings == []
    t = sec(r, "ANOVA")
    assert t.columns == ["Source", "SS", "df", "MS", "% of total", "F", "DFn", "DFd", "P"]
    assert [row[0] for row in t.rows] == ["Interaction", "Row factor", "Column factor", "Residual"]
    assert t.rows[1] == ["Row factor", 1.0, 1.0, 1.0, 10.0, 5.0, 1.0, 6.0, pv(0.01)]
    assert t.rows[3][5:] == [None, None, None, None]


def test_glm_subject_terms(tmp_path):
    table = {"residual": node(4, 3, 1.0, 4.0),
             "matchedFactorVsColFactor": node(2, 3, 0.7, 2.0),
             "matchedFactorVsRowFactor": node(1, 3, 0.3, 1.0),
             "matchedFactor": node(9, 3, 3.0, 9.0, 2.0),
             "rowFactor": node(1, 1, 1, 10.0, 5.0), "total": {"ss": 20.0, "df": 11.0}}
    r = run(tmp_path, res({"anovaTable": table}, GLM), {"experimentalDesign": "REPEATED_MEASURES_BY_BOTH_FACTORS"})
    names = [row[0] for row in sec(r, "ANOVA").rows]
    assert names == ["Row factor", "Subjects", "Subjects x Row factor", "Subjects x Column factor",
                     "Residual", "Total"]


def test_unknown_anova_keys_last_with_key_name(tmp_path):
    table = {"zeta": node(1, 1, 1), "rowFactor": node(1, 1, 1), "alpha": node(2, 1, 2), "total": node(3, 1, 3)}
    r = run(tmp_path, res({"anovaTable": table}))
    assert [row[0] for row in sec(r, "ANOVA").rows] == ["Row factor", "Total", "zeta", "alpha"]


def reml_model():
    fe = {k: {"fTest": {"status": "VALID", "f": f, "dfNumerator": 1.0, "dfDenominator": 9.0, "pValue": pobj(0.03)}}
          for k, f in (("rowFactorVsColFactor", 7.7), ("colFactor", 6.6), ("rowFactor", 5.1))}
    return {"fixedEffects": fe,
            "randomEffects": {"extra": {"sd": 0.1, "variance": 0.01},
                              "residual": {"sd": 0.5, "variance": 0.25},
                              "matchedFactor": {"sd": 0.8, "variance": 0.64}},
            "matchingTest": {"status": "VALID", "chiSquared": 2.7, "df": 1.0, "pValue": pobj(0.09, False)},
            "differenceBetweenColMeans": {"mean1": 1.0, "difference": 0.5,
                                          "differenceCI": {"lower": 0.1, "upper": 0.9, "level": 0.05}}}


def test_reml_fixed_and_random(tmp_path):
    r = run(tmp_path, res(reml_model(), REML), {"experimentalDesign": "REPEATED_MEASURES_BY_ROWS",
            "repeatedMeasures": {"method": "REML"}})
    assert r.kind == "structured" and r.warnings == []
    assert "ANOVA" not in titles(r)
    f = sec(r, "Fixed effects")
    assert f.columns == ["Source", "F", "DFn", "DFd", "P"]
    assert [row[0] for row in f.rows] == ["Row factor", "Column factor", "Interaction"]
    assert f.rows[0][1] == 5.1
    rnd = sec(r, "Random effects")
    assert rnd.columns == ["Source", "SD", "Variance"]
    assert rnd.rows == [["Subject", 0.8, 0.64], ["Residual", 0.5, 0.25], ["extra", 0.1, 0.01]]
    m = sec(r, "Matching")
    assert m.columns == ["Chi-square", "df", "P"] and m.rows == [[2.7, 1.0, pv(0.09, False)]]
    other = [row[0] for row in sec(r, "Other values").rows]
    assert not any(p.startswith("randomEffects") for p in other)
    assert ["differenceBetweenColMeans.differenceCI.level", 0.05] in sec(r, "Other values").rows


def test_reml_without_matching_test(tmp_path):
    m = reml_model()
    del m["matchingTest"]
    r = run(tmp_path, res(m, REML))
    assert "Matching" not in titles(r)


def comp(diff):
    return {"status": "VALID", "meansDifference": diff, "meansDifferenceSE": 0.5, "statistic": 2.0, "df": 6.0,
            "meansDifferenceCI": {"lower": -1.0, "upper": 1.0, "level": 95.0}, "pValueAdjusted": pobj(0.2, False)}


def test_cell_labels(tmp_path):
    id1, id2 = cellid(0, "Day 1", 0, "WT"), cellid(0, "Day 1", 1, "KO")
    mc = {"status": "VALID", "method": "Sidak",
          "tests": PrismBuilder.keyed([(id1, PrismBuilder.keyed([(id2, comp(0.5))]))])}
    r = run(tmp_path, res({"anovaTable": {"rowFactor": node(1, 1, 1)}, "multipleComparisons": mc}))
    s = sec(r, "Multiple comparisons (Sidak)")
    assert s.rows[0][0] == "row 1:Day 1 A:WT vs row 1:Day 1 B:KO"
    assert ["Method", "Sidak"] in sec(r, "Parameters").rows


def test_other_values_keep_level(tmp_path):
    m = {"anovaTable": {"rowFactor": node(1, 1, 1)},
         "differenceBetweenRowMeans": {"differenceCI": {"lower": 0.1, "upper": 0.2, "level": 0.05}},
         "interaction": {"interaction": 0.3},
         "randomEffects": {"matchedFactor": {"sd": 1.0}},
         "dataSummary": {"rowCount": 2, "colCount": 3, "isBalancedDesign": True}}
    r = run(tmp_path, res(m))
    o = sec(r, "Other values")
    assert o.columns == ["Path", "Value"]
    assert ["differenceBetweenRowMeans.differenceCI.level", 0.05] in o.rows
    assert ["interaction.interaction", 0.3] in o.rows
    assert ["randomEffects.matchedFactor.sd", 1.0] in o.rows
    d = sec(r, "Data summary")
    assert d.columns == ["Name", "Value"]
    assert d.rows == [["Row count", 2], ["Column count", 3], ["Balanced design", True]]


def test_sphericity_parameter(tmp_path):
    m = {"factorNames": {"rowFactor": "Region", "colFactor": "Genotype"},
         "anovaTable": {"rowFactor": node(1, 1, 1)}}
    p = {"experimentalDesign": "REPEATED_MEASURES_BY_BOTH_FACTORS",
         "repeatedMeasures": {"method": "OPTIONAL", "assumeSphericity": True}}
    r = run(tmp_path, res(m, GLM), p)
    assert sec(r, "Parameters").rows == [
        ["Design", "REPEATED_MEASURES_BY_BOTH_FACTORS"], ["Repeated measures method", "OPTIONAL"],
        ["Assume sphericity", True],
        ["Post test design", "COMPARE_CELLS_BY_COLUMNS_WITHIN_ROWS_SINGLE_FAMILY"],
        ["Row factor", "Region"], ["Column factor", "Genotype"]]


def test_sphericity_false_is_kept(tmp_path):
    r = run(tmp_path, res({"anovaTable": {"rowFactor": node(1, 1, 1)}}))
    assert ["Assume sphericity", False] in sec(r, "Parameters").rows


def test_missing_model_falls_back(tmp_path):
    r = run(tmp_path, {"status": OK, "dataSummary": {}})
    assert r.kind == "generic"
    assert "Structured reader failed (KeyError), showing generic values." in r.warnings


def test_non_dict_model_falls_back(tmp_path):
    r = run(tmp_path, {"status": OK, ORD: 3})
    assert r.kind == "generic"


def test_garbage_values_do_not_raise(tmp_path):
    m = {"anovaTable": {"rowFactor": {"ss": "undefined", "fTest": "x"}, "residual": 3, "other": []},
         "multipleComparisons": {"method": 7, "tests": {"k": {"id": {}, "value": {"h": {"id": {}, "value": 5}}}}},
         "dataSummary": 5, "factorNames": 4}
    r = run(tmp_path, res(m), {"repeatedMeasures": 3, "postTests": []})
    assert r.kind == "structured"


def test_garbage_reml_does_not_raise(tmp_path):
    r = run(tmp_path, res({"fixedEffects": {"rowFactor": 5, "colFactor": {"fTest": 2}},
                           "randomEffects": {"matchedFactor": 1}, "matchingTest": "x"}, REML))
    assert r.kind == "structured"


def test_no_tests_has_no_comparisons(tmp_path):
    r = run(tmp_path, res({"anovaTable": {"rowFactor": node(1, 1, 1)}}))
    assert "Multiple comparisons" not in titles(r)


def test_glm_without_subjects_row_warns(tmp_path):
    m = {"anovaTable": {"rowFactor": node(1, 1, 1)}}
    r = run(tmp_path, res(m, GLM), {"experimentalDesign": "REPEATED_MEASURES_BY_BOTH_FACTORS"})
    assert "Subjects row only in Prism's rendered table (view ANOVA results)." in r.warnings


def test_no_subjects_warning_when_present_or_not_glm(tmp_path):
    m = {"anovaTable": {"rowFactor": node(1, 1, 1), "matchedFactor": node(9, 3, 3.0)}}
    assert run(tmp_path, res(m, GLM), rm_params({"method": "OPTIONAL", "assumeSphericity": True})).warnings == []
    assert run(tmp_path, res({"anovaTable": {"rowFactor": node(1, 1, 1)}})).warnings == []


def test_gg_epsilon_column(tmp_path):
    t = {"rowFactor": {**node(1, 1, 1, 10.0, 5.0), "ggEpsilon": 0.53}, "residual": node(4, 12, 0.3, 40.0)}
    r = run(tmp_path, res({"anovaTable": t, "matchedFactor": 1}, GLM))
    s = sec(r, "ANOVA")
    assert s.columns[-1] == "GG epsilon" and len(s.columns) == 10
    assert [row[-1] for row in s.rows] == [0.53, None]
    t2 = {"rowFactor": node(1, 1, 1, 10.0, 5.0)}
    assert sec(run(tmp_path, res({"anovaTable": t2})), "ANOVA").columns[-1] == "P"


def test_families_parameters(tmp_path):
    mc = {"status": "VALID", "method": "Sidak", "familyCount": 5, "comparisonPerFamilyCount": 0}
    r = run(tmp_path, res({"anovaTable": {"rowFactor": node(1, 1, 1)}, "multipleComparisons": mc}))
    rows = sec(r, "Parameters").rows
    assert ["Comparison families", 5.0] in rows and ["Comparisons per family", 0.0] in rows


def test_compact_letter_display(tmp_path):
    cld = {"samples": {"a": {"id": cellid(1, "T", 0, "WT"), "value": "B"},
                       "b": {"id": cellid(0, "E", 0, "WT"), "value": "A"}}}
    r = run(tmp_path, res({"anovaTable": {"rowFactor": node(1, 1, 1)}, "compactLetterDisplay": cld}))
    s = sec(r, "Compact letter display")
    assert s.columns == ["Cell", "Group"]
    assert s.rows == [["row 1:E A:WT", "A"], ["row 2:T A:WT", "B"]]


def test_comparison_sample_columns(tmp_path):
    id1, id2 = cellid(0, "Day 1", 0, "WT"), cellid(0, "Day 1", 1, "KO")
    c = comp(0.5)
    c["sample1"], c["sample2"] = {"value": {"mean": 3.0, "n": 4}}, {"value": {"mean": 2.5, "n": 5}}
    mcs = {"status": "VALID", "method": "Sidak",
           "tests": PrismBuilder.keyed([(id1, PrismBuilder.keyed([(id2, c)]))])}
    r = run(tmp_path, res({"anovaTable": {"rowFactor": node(1, 1, 1)}, "multipleComparisons": mcs}))
    s = sec(r, "Multiple comparisons (Sidak)")
    assert s.columns[:5] == ["Comparison", "Mean 1", "n 1", "Mean 2", "n 2"]
    assert s.rows[0][1:5] == [3.0, 4.0, 2.5, 5.0]
