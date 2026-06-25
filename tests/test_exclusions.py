"""Tests for outlier detection (stats_extra) and exclusion/marking (exclusions)."""

from types import SimpleNamespace
import os

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd

from PyFLASH import exclusions, pipeline
from PyFLASH.stats_extra import flag_outliers, iqr_bounds, mad_modified_z
from PyFLASH.utils import EXCLUDED_SENTINEL_PREFIX, excluded_outlier_token
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


def test_excluded_token_helper():
    assert excluded_outlier_token() == EXCLUDED_SENTINEL_PREFIX
    assert excluded_outlier_token("iqr") == f"{EXCLUDED_SENTINEL_PREFIX}:iqr"


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
        data_path, "Adjusted Correlation Pipeline", "_runs_index.csv")
    assert os.path.isfile(index_path)
    idx = pd.read_csv(index_path)
    assert "adj_idx" in set(idx["run_label"].astype(str))
