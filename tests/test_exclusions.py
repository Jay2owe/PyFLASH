"""Tests for outlier detection (stats_extra) and exclusion/marking (exclusions)."""

from types import SimpleNamespace
import os

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd

from PyFLASH import exclusions, pipeline
from PyFLASH.stats_extra import (
    flag_outliers,
    iqr_bounds,
    mad_modified_z,
    rout_outlier_stats,
)
from PyFLASH.utils import (
    EXCLUDED_SENTINEL_PREFIX, EXCLUDED_OUTLIER_PREFIX, EXCLUDED_MANUAL_PREFIX,
    excluded_outlier_token, excluded_manual_token,
)
from PyFLASH.modelling import _to_numeric_excluding_not_included
from PyFLASH.plotting import _prepare_matrix_numeric_df


def _exp(tmp_path, n=24):
    rng = np.random.default_rng(3)
    a = rng.normal(5.0, 1.0, n)
    b = rng.normal(10.0, 1.0, n)
    a[4] = 500.0          # planted outlier in A on animal S04
    b[4] = 500.0          # S04 also an outlier in B -> 2 metrics (animal candidate)
    summary = pd.DataFrame({
        "AnimalName": [f"S{i:02d}" for i in range(n)],
        "Condition": (["WT"] * (n // 2)) + (["KO"] * (n - n // 2)),
        "A": a, "B": b, "C": rng.normal(0.0, 1.0, n),
    })
    fig_path = str(tmp_path / "Python Figures")
    data_path = str(tmp_path / "Data and Stats")
    os.makedirs(fig_path, exist_ok=True)
    os.makedirs(data_path, exist_ok=True)
    return SimpleNamespace(summary=summary, summaries={"SCN": summary},
                           fig_path=fig_path, data_path=data_path,
                           condition_list=[])


# ── stats_extra detection ────────────────────────────────────────────────────
def test_flag_outliers_finds_extreme_value():
    df = pd.DataFrame({"x": [1.0, 2.0, 3.0, 4.0, 5.0, 100.0]})
    flagged = flag_outliers(df, ["x"], methods=("mad",))
    assert set(flagged["row"]) == {5}
    assert bool(flagged.iloc[0]["mad_outlier"])

    lower, upper = iqr_bounds([1, 2, 3, 4, 5, 100])
    assert np.isfinite(lower) and np.isfinite(upper)
    z = mad_modified_z([1, 2, 3, 4, 5, 100])
    assert abs(z[-1]) > 3.5


def test_flag_outliers_supports_rout_method():
    df = pd.DataFrame({"x": [1.0, 2.0, 3.0, 4.0, 5.0, 100.0]})
    flagged = flag_outliers(df, ["x"], methods=("rout",), rout_q=1.0)

    assert set(flagged["row"]) == {5}
    assert bool(flagged.iloc[0]["rout_outlier"])
    assert not bool(flagged.iloc[0]["iqr_outlier"])
    assert not bool(flagged.iloc[0]["mad_outlier"])

    flags, pvals, thresholds, _tvals, center, rsdr = rout_outlier_stats(
        [1, 2, 3, 4, 5, 100], q=1.0)
    assert bool(flags[-1])
    assert np.isfinite(pvals[-1])
    assert np.isfinite(thresholds[-1])
    assert np.isfinite(center)
    assert np.isfinite(rsdr)


def test_flag_outliers_respects_group_labels():
    df = pd.DataFrame({"x": [1.0, 1.1, 0.9, 1.0, 50.0, 0.0, 0.1, -0.1, 0.0, 9.0]})
    labels = pd.Series(["g1"] * 5 + ["g2"] * 5, index=df.index)
    flagged = flag_outliers(df, ["x"], group_labels=labels, methods=("mad",))
    by_group = dict(zip(flagged["row"], flagged["group"]))
    assert by_group.get(4) == "g1"   # the 50.0 is a g1 outlier
    assert by_group.get(9) == "g2"   # the 9.0 is a g2 outlier


# ── cell-level exclusion ─────────────────────────────────────────────────────
def test_exclude_outliers_cell_blanks_value_non_destructively(tmp_path):
    exp = _exp(tmp_path)

    cleaned = exclusions.exclude_outliers(exp, methods=("mad",), scope="cell",
                                          verbose=False)

    cdf = cleaned.summaries["SCN"]
    assert str(cdf.loc[4, "A"]).startswith(EXCLUDED_SENTINEL_PREFIX)
    assert str(cdf.loc[4, "B"]).startswith(EXCLUDED_SENTINEL_PREFIX)
    # A non-flagged metric for the same animal is untouched.
    assert not str(cdf.loc[4, "C"]).startswith(EXCLUDED_SENTINEL_PREFIX)
    # The original experiment is never mutated.
    assert exp.summaries["SCN"].loc[4, "A"] == 500.0

    # Ledger records the affected cells and their original values.
    led = cleaned.exclusions
    a4 = led[(led["AnimalName"] == "S04") & (led["column"] == "A")].iloc[0]
    assert float(a4["original_value"]) == 500.0
    assert a4["scope"] == "cell"
    assert cleaned.exclusion_summary["n_excluded_cells"] >= 2


def test_excluded_value_is_ignored_downstream(tmp_path):
    exp = _exp(tmp_path)
    cleaned = exclusions.exclude_outliers(exp, methods=("mad",), scope="cell",
                                          verbose=False)
    cdf = cleaned.summaries["SCN"]

    # The numeric-coercion entry points treat the token as missing, not as a
    # column-invalidating string: columns survive, the excluded cell -> NaN.
    num, keep, _drop = _prepare_matrix_numeric_df(
        cdf, ["A", "B", "C"], require_complete_numeric=True)
    assert set(keep) == {"A", "B", "C"}
    assert np.isnan(num.loc[4, "A"])
    assert np.isnan(_to_numeric_excluding_not_included(cdf["A"]).loc[4])


# ── animal-level exclusion ───────────────────────────────────────────────────
def test_exclude_outliers_animal_blanks_all_metrics(tmp_path):
    exp = _exp(tmp_path)

    cleaned = exclusions.exclude_outliers(
        exp, methods=("mad",), scope="animal", animal_min_flags=2, verbose=False)

    cdf = cleaned.summaries["SCN"]
    # S04 is flagged on A and B (>=2 metrics), so EVERY metric is blanked for it.
    for col in ("A", "B", "C"):
        assert str(cdf.loc[4, col]).startswith(EXCLUDED_SENTINEL_PREFIX)


# ── mark (non-destructive) then apply ────────────────────────────────────────
def test_mark_then_apply_realises_exclusions(tmp_path):
    exp = _exp(tmp_path)

    marked = exclusions.mark_outliers(exp, methods=("mad",), scope="cell",
                                      verbose=False)
    # Marking changes nothing in the data, only records the ledger.
    assert marked.summaries["SCN"].loc[4, "A"] == 500.0
    assert not marked.exclusions.empty

    applied = exclusions.apply_exclusions(marked)
    assert str(applied.summaries["SCN"].loc[4, "A"]).startswith(
        EXCLUDED_SENTINEL_PREFIX)


def test_apply_exclusions_explicit_cells(tmp_path):
    exp = _exp(tmp_path)

    cleaned = exclusions.apply_exclusions(exp, cells=[("S04", "A")])
    assert str(cleaned.summaries["SCN"].loc[4, "A"]).startswith(
        EXCLUDED_SENTINEL_PREFIX)
    assert cleaned.summaries["SCN"].loc[4, "B"] == 500.0  # not requested
    assert exp.summaries["SCN"].loc[4, "A"] == 500.0      # original untouched


def test_exclude_outliers_accepts_precomputed_outliers(tmp_path):
    exp = _exp(tmp_path)
    ov = pipeline.data_overview(
        exp, outlier_methods=("mad",), include_inventory=False,
        include_group_counts=False, include_descriptives=False,
        include_normality=False, include_covariation=False,
        save=False, verbose=False)

    cleaned = exclusions.exclude_outliers(
        exp, outliers=ov["outliers"], scope="cell", verbose=False)
    assert str(cleaned.summaries["SCN"].loc[4, "A"]).startswith(
        EXCLUDED_SENTINEL_PREFIX)


# ── QC accounting of excluded cells ──────────────────────────────────────────
def test_overview_counts_excluded_separately(tmp_path):
    exp = _exp(tmp_path)
    cleaned = exclusions.exclude_outliers(exp, methods=("mad",), scope="cell",
                                          verbose=False)

    res = pipeline.data_overview(cleaned, save=False, verbose=False)
    inv = res["column_inventory"].set_index("column")
    # Excluded cells are counted as excluded, not present or missing.
    led = cleaned.exclusions
    n_a_excluded = int((led["column"] == "A").sum())
    assert n_a_excluded >= 1
    assert "S04" in set(led[led["column"] == "A"]["AnimalName"])
    assert int(inv.loc["A", "n_excluded"]) == n_a_excluded
    assert int(inv.loc["A", "n_missing"]) == 0
    assert int(inv.loc["A", "n_present"]) == (
        len(cleaned.summaries["SCN"]) - n_a_excluded)


def test_excluded_token_helpers():
    assert excluded_outlier_token() == EXCLUDED_OUTLIER_PREFIX
    assert excluded_outlier_token("iqr") == f"{EXCLUDED_OUTLIER_PREFIX}:iqr"
    assert excluded_manual_token("damaged") == f"{EXCLUDED_MANUAL_PREFIX}:damaged"
    # Both kinds share the family prefix the coercion paths recognise.
    assert excluded_outlier_token().startswith(EXCLUDED_SENTINEL_PREFIX)
    assert excluded_manual_token().startswith(EXCLUDED_SENTINEL_PREFIX)


# ── manual animal exclusion with a reason ────────────────────────────────────
def test_exclude_animals_with_reason(tmp_path):
    exp = _exp(tmp_path)

    clean = exclusions.exclude_animals(exp, "S07", reason="damaged section",
                                       verbose=False)

    cdf = clean.summaries["SCN"]
    # Every metric in S07's row carries the manual sentinel WITH the reason.
    for col in ("A", "B", "C"):
        assert cdf.loc[7, col] == f"{EXCLUDED_MANUAL_PREFIX}:damaged section"
    # Ledger records the reason and kind; downstream ignores the cells.
    led = clean.exclusions
    s07 = led[led["AnimalName"] == "S07"]
    assert set(s07["reason"]) == {"damaged section"}
    assert set(s07["kind"]) == {"manual"}
    assert np.isnan(_to_numeric_excluding_not_included(cdf["A"]).loc[7])
    # Original untouched; summary reports the reason.
    assert np.isfinite(exp.summaries["SCN"].loc[7, "A"])
    assert clean.exclusion_summary["reasons"] == ["damaged section"]


def test_exclude_animals_per_animal_reasons(tmp_path):
    exp = _exp(tmp_path)

    clean = exclusions.exclude_animals(
        exp, {"S07": "damaged", "S08": "wrong genotype"}, verbose=False)

    cdf = clean.summaries["SCN"]
    assert cdf.loc[7, "A"] == f"{EXCLUDED_MANUAL_PREFIX}:damaged"
    assert cdf.loc[8, "A"] == f"{EXCLUDED_MANUAL_PREFIX}:wrong genotype"
    assert clean.exclusion_summary["n_animals_affected"] == 2


def test_exclude_animals_specific_columns(tmp_path):
    exp = _exp(tmp_path)

    clean = exclusions.exclude_animals(exp, "S07", reason="bad A",
                                       columns=["A"], verbose=False)

    cdf = clean.summaries["SCN"]
    assert str(cdf.loc[7, "A"]).startswith(EXCLUDED_MANUAL_PREFIX)
    assert np.isfinite(cdf.loc[7, "B"])  # other metrics retained


def test_mark_animals_then_apply(tmp_path):
    exp = _exp(tmp_path)

    marked = exclusions.mark_animals(exp, "S07", reason="qc fail", verbose=False)
    assert np.isfinite(marked.summaries["SCN"].loc[7, "A"])  # unchanged
    assert not marked.exclusions.empty

    applied = exclusions.apply_exclusions(marked)
    assert str(applied.summaries["SCN"].loc[7, "A"]).startswith(
        EXCLUDED_MANUAL_PREFIX)


# ── pipeline_io: adjusted-correlation now writes a runs index ─────────────────
def test_adjusted_correlation_writes_runs_index(tmp_path):
    rng = np.random.default_rng(1)
    n = 30
    age = np.linspace(50, 85, n)
    summary = pd.DataFrame({
        "AnimalName": [f"S{i:02d}" for i in range(n)],
        "A": 0.8 * age + rng.normal(0, 1.0, n),
        "B": -0.7 * age + rng.normal(0, 1.0, n),
        "C": rng.normal(0, 1, n),
    })
    fig_path = str(tmp_path / "Python Figures")
    data_path = str(tmp_path / "Data and Stats")
    os.makedirs(fig_path, exist_ok=True)
    os.makedirs(data_path, exist_ok=True)
    exp = SimpleNamespace(summary=summary, summaries={"SCN": summary},
                          fig_path=fig_path, data_path=data_path, condition_list=[])

    pipeline.adjusted_correlation(
        exp, endpoints=["A", "B", "C"], tests=("pearsonr",), gate="p",
        max_adjusted_regressions=0, run_label="adj_idx", save=True, verbose=False)

    index_path = os.path.join(
        fig_path, "Adjusted Correlation Pipeline", "_runs_index.csv")
    assert os.path.isfile(index_path)
    idx = pd.read_csv(index_path)
    assert "adj_idx" in set(idx["run_label"].astype(str))


# ── excluded values flow correctly into adjusted_correlation ──────────────────
def test_excluded_endpoint_stays_numeric_in_adjusted_correlation(tmp_path):
    rng = np.random.default_rng(2)
    n = 30
    age = np.linspace(50, 85, n)
    summary = pd.DataFrame({
        "AnimalName": [f"S{i:02d}" for i in range(n)],
        "A": 0.8 * age + rng.normal(0, 1.0, n),
        "B": -0.7 * age + rng.normal(0, 1.0, n),
        "C": rng.normal(0, 1, n),
    })
    fig_path = str(tmp_path / "Python Figures")
    data_path = str(tmp_path / "Data and Stats")
    os.makedirs(fig_path, exist_ok=True)
    os.makedirs(data_path, exist_ok=True)
    exp = SimpleNamespace(summary=summary, summaries={"SCN": summary},
                          fig_path=fig_path, data_path=data_path, condition_list=[])

    # Excluding one A value makes A object dtype (it now holds a token).
    cleaned = exclusions.apply_exclusions(exp, cells=[("S05", "A")])
    assert cleaned.summaries["SCN"]["A"].dtype == object

    res = pipeline.adjusted_correlation(
        cleaned, endpoints=["A", "B", "C"], tests=("pearsonr",), gate="p",
        categorical="auto", max_adjusted_regressions=0, save=False, verbose=False)
    # A must stay a numeric endpoint, NOT be auto-classified categorical.
    assert "A" not in res["categorical"]
    assert "A" in res["final_endpoints"]


# ── mark(fill=np.nan) realises NaN on apply ──────────────────────────────────
def test_mark_with_nan_fill_then_apply_realises_nan(tmp_path):
    exp = _exp(tmp_path)

    marked = exclusions.mark_outliers(exp, methods=("mad",), scope="cell",
                                      fill=np.nan, verbose=False)
    assert marked.summaries["SCN"].loc[4, "A"] == 500.0  # mark changes nothing

    applied = exclusions.apply_exclusions(marked)
    val = applied.summaries["SCN"].loc[4, "A"]
    assert isinstance(val, float) and np.isnan(val)  # realised as NaN, not a token


# ── missingness map distinguishes excluded cells ─────────────────────────────
def test_missingness_codes_mark_excluded(tmp_path):
    from PyFLASH.pipeline import _ovw_missingness_codes

    exp = _exp(tmp_path)
    cleaned = exclusions.exclude_outliers(exp, methods=("mad",), scope="cell",
                                          verbose=False)
    cdf = cleaned.summaries["SCN"]
    codes = _ovw_missingness_codes(cdf, ["A", "B", "C"])

    assert codes[4, 0] == 3          # S04/A excluded -> code 3
    assert codes[0, 2] == 0          # an untouched cell -> present
    assert (codes == 3).any()


# ── cleaned copy keeps a consistent plain `.summary` attribute ────────────────
def test_cleaned_copy_summary_attribute_is_consistent(tmp_path):
    exp = _exp(tmp_path)

    cleaned = exclusions.exclude_outliers(exp, methods=("mad",), scope="cell",
                                          verbose=False)
    # A downstream reading `.summary` directly sees the cleaned table.
    assert cleaned.summary is cleaned.summaries["SCN"]
    assert str(cleaned.summary.loc[4, "A"]).startswith(EXCLUDED_SENTINEL_PREFIX)
    assert exp.summary.loc[4, "A"] == 500.0  # original untouched


# ── numeric column with an excluded token AND a real NaN stays numeric ────────
def test_excluded_numeric_with_real_nan_not_categorical(tmp_path):
    rng = np.random.default_rng(4)
    n = 30
    age = np.linspace(50, 85, n)
    a = 0.8 * age + rng.normal(0, 1.0, n)
    a[3] = np.nan  # a genuine missing value, in addition to the excluded cell
    summary = pd.DataFrame({
        "AnimalName": [f"S{i:02d}" for i in range(n)],
        "A": a,
        "B": -0.7 * age + rng.normal(0, 1.0, n),
        "C": rng.normal(0, 1, n),
        "Sex": np.where(np.arange(n) % 2 == 0, "F", "M"),
    })
    fig_path = str(tmp_path / "Python Figures")
    data_path = str(tmp_path / "Data and Stats")
    os.makedirs(fig_path, exist_ok=True)
    os.makedirs(data_path, exist_ok=True)
    exp = SimpleNamespace(summary=summary, summaries={"SCN": summary},
                          fig_path=fig_path, data_path=data_path, condition_list=[])

    cleaned = exclusions.apply_exclusions(exp, cells=[("S05", "A")])
    res = pipeline.adjusted_correlation(
        cleaned, endpoints=["A", "B", "C"], covariates=["Sex"],
        categorical="auto", reference_levels={"Sex": "F"}, tests=("pearsonr",),
        gate="p", max_adjusted_regressions=0, save=False, verbose=False)

    assert "A" not in res["categorical"]   # numeric despite token + real NaN
    assert "Sex" in res["categorical"]      # genuine categorical still categorical


def test_adjusted_slug_stable_across_equivalent_settings():
    from PyFLASH.pipeline import _adj_corr_slug

    s1 = _adj_corr_slug(
        ["A", "B"], ["Sex", "Geno"], [], ("pearsonr",), "fdr", 0.05, "all", None,
        settings={"reference_levels": {"Sex": "F", "Geno": "WT"},
                  "categorical": {"Sex", "Geno"}})
    s2 = _adj_corr_slug(
        ["A", "B"], ["Sex", "Geno"], [], ("pearsonr",), "fdr", 0.05, "all", None,
        settings={"reference_levels": {"Geno": "WT", "Sex": "F"},
                  "categorical": {"Geno", "Sex"}})
    assert s1 == s2  # dict/set ordering must not change the slug
    s3 = _adj_corr_slug(
        ["A", "B"], ["Sex", "Geno"], [], ("pearsonr",), "fdr", 0.05, "all", None,
        settings={"reference_levels": {"Sex": "M"}, "categorical": {"Sex"}})
    assert s3 != s1  # a materially different config still differs
    # max_adjusted_regressions changes which regression rows are written.
    s4 = _adj_corr_slug(
        ["A", "B"], [], [], ("pearsonr",), "fdr", 0.05, "all", None,
        settings={"max_adjusted_regressions": 4})
    s5 = _adj_corr_slug(
        ["A", "B"], [], [], ("pearsonr",), "fdr", 0.05, "all", None,
        settings={"max_adjusted_regressions": 8})
    assert s4 != s5


def test_correlation_slug_encodes_min_n():
    from PyFLASH.plotting import _corr_pipeline_slug

    base = dict(columns=["A", "B"], against_columns=[], methods=["pearsonr"],
                require="and", gate="fdr", alpha=0.05, by="all", factor=None,
                specificity=None, roi="SCN")
    s_a = _corr_pipeline_slug(**base, settings={"min_n": 3})
    s_b = _corr_pipeline_slug(**base, settings={"min_n": 8})
    assert s_a != s_b  # min_n changes which pairs are included -> different run
    # Equivalent settings (different dict order) still collapse.
    s_c = _corr_pipeline_slug(**base, settings={"min_n": 3, "normalize_x": False})
    s_d = _corr_pipeline_slug(**base, settings={"normalize_x": False, "min_n": 3})
    assert s_c == s_d


def test_pie_valid_row_mask_drops_excluded(tmp_path):
    from PyFLASH.plotting import _pie_valid_row_mask

    s = pd.Series(["WT", "KO", f"{EXCLUDED_MANUAL_PREFIX}:damaged", "KO"])
    mask = _pie_valid_row_mask(s)
    assert list(mask) == [True, True, False, True]  # excluded row not counted
