"""Tests for the data_overview pipeline (descriptive / QC overview of a batch)."""

import os
from types import SimpleNamespace

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd
import pytest

from PyFLASH import pipeline
from PyFLASH.spec import PLOT_REGISTRY, _resolve_func


def _overview_dataset(tmp_path, n=24):
    rng = np.random.default_rng(7)
    a = rng.normal(10.0, 2.0, n)
    b = 2.0 * a + rng.normal(0, 0.05, n)          # near-perfectly covaries with A
    c = rng.normal(10.0, 1.0, n)
    c[5] = 1000.0                                  # planted outlier on animal S05
    # A column that mixes a sentinel cell and a true-NaN cell with real numbers.
    mixed = pd.Series(rng.normal(3.0, 0.5, n))
    mixed = mixed.astype(object)
    mixed.iloc[0] = "NOT_INCLUDED_IN_EXPERIMENT"
    mixed.iloc[1] = np.nan

    summary = pd.DataFrame({
        "AnimalName": [f"S{i:02d}" for i in range(n)],
        "Condition": (["WT"] * (n // 2)) + (["KO"] * (n - n // 2)),
        "Diagnosis": (["Control"] * (n // 2)) + (["AD"] * (n - n // 2)),
        "Sex": np.where(np.arange(n) % 2 == 0, "F", "M"),
        "numSections": rng.integers(2, 5, n),
        "A": a,
        "B": b,
        "C": c,
        "M1": mixed,
        "Const": np.full(n, 5.0),
    })
    fig_path = str(tmp_path / "Python Figures")
    data_path = str(tmp_path / "Data and Stats")
    os.makedirs(fig_path, exist_ok=True)
    os.makedirs(data_path, exist_ok=True)
    return SimpleNamespace(
        summary=summary,
        summaries={"SCN": summary},
        fig_path=fig_path,
        data_path=data_path,
        # Real condition objects so by="conditions" actually panels the
        # descriptive/normality/outlier sections (names match the Condition col).
        condition_list=[SimpleNamespace(name="WT"), SimpleNamespace(name="KO")],
    )


def test_registry_alias_resolves_to_data_overview():
    assert "data_overview_pipeline" in PLOT_REGISTRY
    func = _resolve_func(PLOT_REGISTRY["data_overview_pipeline"])
    assert func is pipeline.data_overview


def test_data_overview_classifies_columns_and_counts_sentinel_vs_nan(tmp_path):
    exp = _overview_dataset(tmp_path)

    res = pipeline.data_overview(exp, run_label="overview_basic", save=True)

    inv = res["column_inventory"].set_index("column")
    # dtype classification: numeric metrics vs string/identifier/constant.
    assert inv.loc["A", "role"] == "numeric"
    assert inv.loc["B", "role"] == "numeric"
    assert inv.loc["Sex", "role"] == "categorical"
    assert inv.loc["AnimalName", "role"] == "identifier"
    assert inv.loc["Const", "role"] == "constant"
    counts = res["inventory_counts"]
    assert counts.get("numeric", 0) >= 3

    # Sentinel ("not measured") is counted separately from a true NaN ("missing").
    assert int(inv.loc["M1", "n_sentinel"]) == 1
    assert int(inv.loc["M1", "n_missing"]) == 1
    # pct_missing is true-NaN only; pct_unavailable folds in the sentinel too.
    assert inv.loc["M1", "pct_missing"] == round(100.0 / 24, 2)
    assert inv.loc["M1", "pct_unavailable"] == round(200.0 / 24, 2)

    # Files written into the run folder.
    data_dir = res["data_dir"]
    for fname in ("manifest.json", "column_inventory.csv", "group_counts.csv",
                  "descriptive_stats.csv", "normality.csv", "outliers.csv",
                  "outlier_animals.csv", "covariation_pairs.csv",
                  "covariation_matrix.csv", "condition_distribution_stats.csv",
                  "condition_fingerprint.csv", "condition_variability.csv",
                  "effect_sizes.csv"):
        assert os.path.isfile(os.path.join(data_dir, fname)), fname
    for fname in (
        "Availability by Condition.svg",
        "Condition Distribution Z Scores.svg",
        "Condition Distributions.svg",
        "Condition Fingerprint.svg",
        "Condition Variability.svg",
        "Covariation Matrix.svg",
        "Covariation Pairs.svg",
        "Descriptive Summary.svg",
        "Effect Size Forest.svg",
        "Group Counts.svg",
        "Metric Distributions.svg",
        "Missingness Map.svg",
        "Normality Summary.svg",
        "Outlier Summary.svg",
    ):
        assert os.path.isfile(os.path.join(res["fig_dir"], fname)), fname

    assert res["condition_distribution_groups"] == ["WT", "KO"]
    cds = res["condition_distributions"]
    assert set(cds["group"]) == {"WT", "KO"}
    assert {"A", "B", "C"}.issubset(set(cds["column"]))
    wt_a = cds[(cds["group"] == "WT") & (cds["column"] == "A")].iloc[0]
    assert int(wt_a["n"]) == 12
    assert not res["condition_fingerprint"].empty
    assert not res["condition_variability"].empty
    effects = res["effect_sizes"]
    assert set(effects["control"]) == {"WT"}
    assert set(effects["group"]) == {"KO"}
    assert {"A", "B", "C"}.issubset(set(effects["column"]))


def test_data_overview_flags_planted_outlier_animal(tmp_path):
    exp = _overview_dataset(tmp_path)

    res = pipeline.data_overview(exp, run_label="overview_outlier", save=False)

    animals = res["outlier_animals"]
    assert "S05" in set(animals["AnimalName"])
    flagged = res["outliers"]
    s05_C = flagged[(flagged["AnimalName"] == "S05") & (flagged["column"] == "C")]
    assert not s05_C.empty
    assert bool(s05_C.iloc[0]["rout_outlier"])
    assert not bool(s05_C.iloc[0]["iqr_outlier"])
    assert not bool(s05_C.iloc[0]["mad_outlier"])


def test_data_overview_can_use_legacy_iqr_mad_screen(tmp_path):
    exp = _overview_dataset(tmp_path)

    res = pipeline.data_overview(
        exp, outlier_methods=("iqr", "mad"), run_label="overview_iqr_mad",
        save=False)

    flagged = res["outliers"]
    s05_C = flagged[(flagged["AnimalName"] == "S05") & (flagged["column"] == "C")]
    assert not s05_C.empty
    assert bool(s05_C.iloc[0]["iqr_outlier"])
    assert bool(s05_C.iloc[0]["mad_outlier"])
    assert not bool(s05_C.iloc[0]["rout_outlier"])


def test_data_overview_detects_covarying_pair(tmp_path):
    exp = _overview_dataset(tmp_path)

    res = pipeline.data_overview(
        exp, covariation_threshold=0.9, run_label="overview_cov", save=False)

    cov = res["covariation"]
    pairs = {frozenset((row["x"], row["y"])) for _, row in cov.iterrows()}
    assert frozenset(("A", "B")) in pairs
    ab = cov[[frozenset((r["x"], r["y"])) == frozenset(("A", "B"))
              for _, r in cov.iterrows()]].iloc[0]
    assert abs(float(ab["r"])) >= 0.9


def test_data_overview_panels_by_condition(tmp_path):
    exp = _overview_dataset(tmp_path)

    res = pipeline.data_overview(
        exp, by="conditions", run_label="overview_by_cond", save=False)

    # group_counts is design-level and always reports per-condition Ns.
    gc = res["group_counts"]
    cond_rows = gc[gc["grouping"] == "Condition"]
    assert set(cond_rows["level"]) == {"WT", "KO"}
    assert int(cond_rows[cond_rows["level"] == "WT"]["n_animals"].iloc[0]) == 12

    # by="conditions" must actually panel the per-group sections (not pool to
    # a single "All" group), so each describes WT and KO separately.
    assert set(res["descriptives"]["group"]) == {"WT", "KO"}
    assert set(res["normality"]["group"]) == {"WT", "KO"}
    # The planted C outlier (S05) sits in the WT half, so it is flagged within WT.
    s05 = res["outliers"][res["outliers"]["AnimalName"] == "S05"]
    assert not s05.empty
    assert set(s05["group"]) == {"WT"}


def test_data_overview_condition_distributions_can_group_by_factor(tmp_path):
    exp = _overview_dataset(tmp_path)

    res = pipeline.data_overview(
        exp,
        factor="Diagnosis",
        effect_control="Control",
        run_label="overview_diag_distributions",
        save=False,
    )

    assert res["condition_distribution_groups"] == ["Control", "AD"]
    dist = res["condition_distributions"]
    assert set(dist["group"]) == {"Control", "AD"}
    assert int(dist[(dist["group"] == "Control") & (dist["column"] == "A")]["n"].iloc[0]) == 12
    effects = res["effect_sizes"]
    assert set(effects["control"]) == {"Control"}
    assert set(effects["group"]) == {"AD"}
    assert effects["hedges_g"].notna().any()


def test_data_overview_specificity_queue_merges_into_one_folder(tmp_path):
    # A specificity queue writes every condition into ONE shared run folder, each
    # condition's tables/figures distinguished by a concise specificity tag.
    exp = _overview_dataset(tmp_path)

    res = pipeline.data_overview(
        exp,
        specificity=[("Diagnosis", "Control"), ("Diagnosis", "AD")],
        run_label="overview_diag_queue",
        save=True,
    )

    assert res.get("queued") is not True
    assert res["pipeline"] == "data_overview"
    assert os.path.basename(res["data_dir"]) == "overview_diag_queue"
    assert os.path.isfile(os.path.join(res["data_dir"], "manifest.json"))
    assert {tuple(c["specificity"]) for c in res["conditions"]} == {
        ("Diagnosis", "Control"), ("Diagnosis", "AD")}
    assert all(c["n_rows"] == 12 for c in res["conditions"])

    # Both conditions' inventories sit flat in one data folder.
    data_files = set(os.listdir(res["data_dir"]))
    assert "column_inventory_Diagnosis.Control.csv" in data_files
    assert "column_inventory_Diagnosis.AD.csv" in data_files
    # One combined overview montage spans the whole queue.
    assert res.get("montage") and os.path.isfile(res["montage"])


def test_data_overview_section_toggles_skip_work(tmp_path):
    exp = _overview_dataset(tmp_path)

    res = pipeline.data_overview(
        exp,
        include_descriptives=False,
        include_normality=False,
        include_outliers=False,
        include_covariation=False,
        include_condition_distributions=False,
        include_effect_sizes=False,
        run_label="overview_inventory_only",
        save=True,
    )

    assert res["descriptives"].empty
    assert res["normality"].empty
    assert res["outliers"].empty
    assert res["covariation"].empty
    assert res["condition_distributions"].empty
    assert res["effect_sizes"].empty
    assert not res["column_inventory"].empty
    data_dir = res["data_dir"]
    assert os.path.isfile(os.path.join(data_dir, "column_inventory.csv"))
    assert not os.path.isfile(os.path.join(data_dir, "descriptive_stats.csv"))
    assert not os.path.isfile(os.path.join(data_dir, "condition_distribution_stats.csv"))
    assert not os.path.isfile(os.path.join(data_dir, "effect_sizes.csv"))
    for fname in (
        "Covariation Matrix.svg",
        "Covariation Pairs.svg",
        "Condition Distribution Z Scores.svg",
        "Condition Distributions.svg",
        "Condition Fingerprint.svg",
        "Condition Variability.svg",
        "Descriptive Summary.svg",
        "Effect Size Forest.svg",
        "Metric Distributions.svg",
        "Normality Summary.svg",
        "Outlier Summary.svg",
    ):
        assert not os.path.isfile(os.path.join(res["fig_dir"], fname)), fname
    for fname in (
        "Availability by Condition.svg",
        "Group Counts.svg",
        "Missingness Map.svg",
    ):
        assert os.path.isfile(os.path.join(res["fig_dir"], fname)), fname


def test_data_overview_role_classification_bool_vs_int(tmp_path):
    n = 10
    summary = pd.DataFrame({
        "AnimalName": [f"S{i:02d}" for i in range(n)],
        "Flag": ([True, False] * (n // 2)),                       # pure bool dtype
        "FlagObj": pd.Series([True, False] * (n // 2), dtype=object),  # object bool
        "Int01": [0, 1] * (n // 2),                               # 0/1 ints, NOT bool
        "Val": np.arange(n, dtype=float),
    })
    # A sentinel keeps FlagObj as object dtype (the case is_bool_dtype would miss).
    summary.loc[0, "FlagObj"] = "NOT_INCLUDED_IN_EXPERIMENT"
    fig_path = str(tmp_path / "Python Figures")
    data_path = str(tmp_path / "Data and Stats")
    os.makedirs(fig_path, exist_ok=True)
    os.makedirs(data_path, exist_ok=True)
    exp = SimpleNamespace(summary=summary, summaries={"SCN": summary},
                          fig_path=fig_path, data_path=data_path, condition_list=[])

    res = pipeline.data_overview(
        exp, include_covariation=False, run_label="roles", save=False)

    inv = res["column_inventory"].set_index("column")
    assert inv.loc["Flag", "role"] == "boolean"
    # Object-dtype bool carrying a sentinel must still classify as boolean.
    assert inv.loc["FlagObj", "role"] == "boolean"
    assert int(inv.loc["FlagObj", "n_sentinel"]) == 1
    # 0/1 integers are a count-like metric, NOT a boolean.
    assert inv.loc["Int01", "role"] == "numeric"


def test_data_overview_runs_index_numeric_without_inventory(tmp_path):
    exp = _overview_dataset(tmp_path)

    res = pipeline.data_overview(
        exp, include_inventory=False, run_label="ovw_noinv", save=True)

    # With the inventory section off, the runs index still records the
    # matrix-numeric column count rather than a misleading zero.
    idx_path = os.path.join(os.path.dirname(res["data_dir"]), "_runs_index.csv")
    assert os.path.isfile(idx_path)
    idx = pd.read_csv(idx_path)
    row = idx[idx["run_label"] == "ovw_noinv"].iloc[0]
    assert res["n_numeric_columns"] > 0
    assert int(row["n_numeric"]) == res["n_numeric_columns"]


def test_data_overview_auto_slug_varies_with_qc_settings(tmp_path):
    exp = _overview_dataset(tmp_path)

    # No explicit run_label: the auto-slug must fold in output-changing QC
    # settings, so two different configs land in different run folders and
    # if_exists='skip' can't return a stale run computed under other settings.
    r1 = pipeline.data_overview(exp, covariation_threshold=0.80, save=False)
    r2 = pipeline.data_overview(exp, covariation_threshold=0.95, save=False)
    assert r1["run_label"] != r2["run_label"]

    r3 = pipeline.data_overview(exp, mad_threshold=3.5, save=False)
    r4 = pipeline.data_overview(exp, mad_threshold=2.0, save=False)
    assert r3["run_label"] != r4["run_label"]
