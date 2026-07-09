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
    assert data_dir == res["fig_dir"]
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
        include_significance_audit=False,
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


# ── Stage 02: flexible condition splitting (split_by / split_mode) ──────────

def test_split_by_condition_matches_by_conditions(tmp_path):
    # A single split key must reproduce the one-axis by="conditions" grouping
    # exactly, so the new resolver is a strict superset of the old behaviour.
    exp = _overview_dataset(tmp_path)

    r_split = pipeline.data_overview(
        exp, split_by="Condition", run_label="split_cond", save=False)
    r_by = pipeline.data_overview(
        exp, by="conditions", run_label="by_cond", save=False)

    assert r_split["groups"] == r_by["groups"] == ["WT", "KO"]
    assert (r_split["condition_distribution_groups"]
            == r_by["condition_distribution_groups"] == ["WT", "KO"])
    assert set(r_split["descriptives"]["group"]) == {"WT", "KO"}
    assert set(r_split["normality"]["group"]) == {"WT", "KO"}


def test_split_by_cross_yields_composite_product_cells(tmp_path):
    # Condition x Sex crossing yields the full 2x2 product with composite labels
    # and AND-intersected animals; each cell holds 6 of the 24 animals.
    exp = _overview_dataset(tmp_path)

    res = pipeline.data_overview(
        exp, split_by=["Condition", "Sex"], split_mode="cross",
        run_label="split_cross", save=False)

    expected = ["WT | F", "WT | M", "KO | F", "KO | M"]
    assert res["groups"] == expected                       # first-key-major order
    assert res["condition_distribution_groups"] == expected
    assert set(res["descriptives"]["group"]) == set(expected)
    cds = res["condition_distributions"]
    wt_f_a = cds[(cds["group"] == "WT | F") & (cds["column"] == "A")].iloc[0]
    assert int(wt_f_a["n"]) == 6


def test_split_by_cross_drops_empty_product_cells(tmp_path):
    # When a product cell has no animals (all WT are F, all KO are M) the empty
    # cells are dropped, leaving only the two populated composites.
    rng = np.random.default_rng(3)
    summary = pd.DataFrame({
        "AnimalName": [f"A{i:02d}" for i in range(12)],
        "Condition": (["WT"] * 6) + (["KO"] * 6),
        "Sex": (["F"] * 6) + (["M"] * 6),
        "numSections": [3] * 12,
        "X": rng.normal(5.0, 1.0, 12),
        "Y": rng.normal(2.0, 0.5, 12),
    })
    fig_path = str(tmp_path / "Python Figures")
    data_path = str(tmp_path / "Data and Stats")
    os.makedirs(fig_path, exist_ok=True)
    os.makedirs(data_path, exist_ok=True)
    exp = SimpleNamespace(
        summary=summary, summaries={"SCN": summary},
        fig_path=fig_path, data_path=data_path,
        condition_list=[SimpleNamespace(name="WT"), SimpleNamespace(name="KO")])

    res = pipeline.data_overview(
        exp, split_by=["Condition", "Sex"], split_mode="cross",
        include_covariation=False, run_label="split_empty", save=False)

    assert res["groups"] == ["WT | F", "KO | M"]           # WT|M and KO|F dropped


def test_split_mode_parallel_concatenates_axes(tmp_path):
    # parallel mode lists each axis independently with key-prefixed labels so
    # Condition and Sex axes never collide.
    exp = _overview_dataset(tmp_path)

    res = pipeline.data_overview(
        exp, split_by=["Condition", "Sex"], split_mode="parallel",
        run_label="split_parallel", save=False)

    assert set(res["groups"]) == {
        "Condition=WT", "Condition=KO", "Sex=F", "Sex=M"}
    assert set(res["descriptives"]["group"]) == {
        "Condition=WT", "Condition=KO", "Sex=F", "Sex=M"}


def test_split_settings_produce_distinct_run_slugs(tmp_path):
    # Distinct grouping settings must hash to distinct run folders so a later run
    # can't reuse (if_exists='skip') a run computed under a different split.
    exp = _overview_dataset(tmp_path)

    single = pipeline.data_overview(exp, split_by="Condition", save=False)
    crossed = pipeline.data_overview(
        exp, split_by=["Condition", "Sex"], split_mode="cross", save=False)
    parallel = pipeline.data_overview(
        exp, split_by=["Condition", "Sex"], split_mode="parallel", save=False)

    slugs = {single["run_label"], crossed["run_label"], parallel["run_label"]}
    assert len(slugs) == 3


def test_split_by_unresolvable_key_raises(tmp_path):
    exp = _overview_dataset(tmp_path)

    with pytest.raises(ValueError):
        pipeline.data_overview(
            exp, split_by="NotAColumn", run_label="bad_key", save=False)
    with pytest.raises(ValueError):
        pipeline.data_overview(
            exp, split_by=["Condition", "NotAColumn"], run_label="bad_key2",
            save=False)


def test_split_effect_control_composite_rule(tmp_path):
    # effect_control="WT" is not a full composite label, so it resolves per
    # remaining-key (Sex) stratum: WT|F controls KO|F and WT|M controls KO|M.
    exp = _overview_dataset(tmp_path)

    res = pipeline.data_overview(
        exp, split_by=["Condition", "Sex"], split_mode="cross",
        effect_control="WT", run_label="split_ctrl", save=False)

    assert res["effect_control"] == "WT"
    effects = res["effect_sizes"]
    assert set(effects["control"]) == {"WT | F", "WT | M"}
    assert set(effects["group"]) == {"KO | F", "KO | M"}
    # controls only ever compare within their own Sex stratum.
    pairs = set(zip(effects["control"], effects["group"]))
    assert pairs == {("WT | F", "KO | F"), ("WT | M", "KO | M")}

    # An exact composite label names a single control across all cells.
    res_exact = pipeline.data_overview(
        exp, split_by=["Condition", "Sex"], split_mode="cross",
        effect_control="WT | F", run_label="split_ctrl_exact", save=False)
    assert res_exact["effect_control"] == "WT | F"
    assert set(res_exact["effect_sizes"]["control"]) == {"WT | F"}
    assert set(res_exact["effect_sizes"]["group"]) == {"WT | M", "KO | F", "KO | M"}

    # An effect_control that is neither a label nor a first-key component errors.
    with pytest.raises(ValueError):
        pipeline.data_overview(
            exp, split_by=["Condition", "Sex"], split_mode="cross",
            effect_control="Nope", run_label="split_ctrl_bad", save=False)


# ── Stage 03: significance audit (auto-select test + concordance + FDR) ──────

_AUDIT_COLUMNS = {
    "marker", "contrast", "left_group", "right_group", "n_left", "n_right",
    "test", "test_partner", "statistic", "p", "p_partner", "q", "reject_fdr",
    "effect_metric", "effect_value", "effect_ci_low", "effect_ci_high",
    "significant", "concordant", "alpha",
}

# The exact test-name strings PyFLASH.stats.multipleComparisons returns.
_AUDIT_TESTS = {
    "Independent T-Test", "Mann-Whitney U", "One-Way ANOVA", "Kruskal-Wallis",
}


def _skewed_three_group_dataset(tmp_path, n_per=8):
    """Three condition groups; ``Skew`` is heavily right-skewed so the pooled
    normality screen fails and the audit must select a non-parametric test."""
    rng = np.random.default_rng(11)
    names = ["G1", "G2", "G3"]
    conditions, skew, norm = [], [], []
    for i, g in enumerate(names):
        conditions += [g] * n_per
        skew.append(rng.exponential(scale=1.5 + 0.4 * i, size=n_per))  # non-normal
        norm.append(rng.normal(10.0 + 0.3 * i, 1.0, size=n_per))
    n = n_per * len(names)
    summary = pd.DataFrame({
        "AnimalName": [f"A{i:02d}" for i in range(n)],
        "Condition": conditions,
        "numSections": rng.integers(2, 5, n),
        "Skew": np.concatenate(skew),
        "Norm": np.concatenate(norm),
    })
    fig_path = str(tmp_path / "Python Figures")
    data_path = str(tmp_path / "Data and Stats")
    os.makedirs(fig_path, exist_ok=True)
    os.makedirs(data_path, exist_ok=True)
    return SimpleNamespace(
        summary=summary, summaries={"SCN": summary},
        fig_path=fig_path, data_path=data_path,
        condition_list=[SimpleNamespace(name=g) for g in names])


def test_significance_audit_frame_shape_and_annotation(tmp_path):
    exp = _overview_dataset(tmp_path)

    res = pipeline.data_overview(
        exp, by="conditions", include_significance_audit=True,
        run_label="audit_basic", save=False)

    audit = res["significance_audit"]
    assert isinstance(audit, pd.DataFrame) and not audit.empty
    assert _AUDIT_COLUMNS.issubset(set(audit.columns))

    # One row per (marker, contrast): 2 groups -> exactly one contrast per marker.
    assert audit.groupby("marker").size().max() == 1
    for col in ("A", "B", "C"):
        rows = audit[audit["marker"] == col]
        assert len(rows) == 1
        row = rows.iloc[0]
        assert row["contrast"] == "KO vs WT"
        assert row["left_group"] == "KO" and row["right_group"] == "WT"
        # Auto-selected 2-group parametric test, annotated with the exact string.
        assert row["test"] in _AUDIT_TESTS
        assert row["test"] == "Independent T-Test"
        assert np.isfinite(row["p"])
        # Partner family (non-parametric) run so a concordance flag can be formed.
        assert row["test_partner"] == "Mann-Whitney U"
        assert np.isfinite(row["p_partner"])
        assert bool(row["concordant"]) in (True, False)
        # Matched effect size + bootstrap CI.
        assert row["effect_metric"] == "hedges_g"
        assert np.isfinite(row["effect_value"])
        assert np.isfinite(row["effect_ci_low"]) and np.isfinite(row["effect_ci_high"])
        assert float(row["alpha"]) == 0.05
        assert bool(row["significant"]) in (True, False)


def test_significance_audit_screen_adds_fdr_with_p_counterpart(tmp_path):
    exp = _overview_dataset(tmp_path)

    res = pipeline.data_overview(
        exp, by="conditions", include_significance_audit=True, screen=True,
        run_label="audit_screen", save=False)

    audit = res["significance_audit"]
    assert {"q", "reject_fdr"}.issubset(set(audit.columns))
    tested = audit[pd.to_numeric(audit["p"], errors="coerce").notna()]
    assert not tested.empty
    # Every q has a finite p counterpart, and q is populated when screening.
    assert pd.to_numeric(tested["q"], errors="coerce").notna().any()
    assert pd.to_numeric(tested["q"], errors="coerce").notna().all()
    assert tested["reject_fdr"].isin([True, False]).all()


def test_significance_audit_gate_fdr_requires_screen(tmp_path):
    exp = _overview_dataset(tmp_path)

    with pytest.raises(ValueError):
        pipeline.data_overview(
            exp, by="conditions", include_significance_audit=True,
            gate="fdr", screen=False, run_label="audit_gate_bad", save=False)


def test_significance_audit_selects_nonparametric_for_skewed_marker(tmp_path):
    exp = _skewed_three_group_dataset(tmp_path)

    res = pipeline.data_overview(
        exp, by="conditions", include_significance_audit=True,
        run_label="audit_kw", save=False)

    audit = res["significance_audit"]
    skew = audit[audit["marker"] == "Skew"]
    # 3 groups -> 3 all-pairs contrasts, each selecting the non-parametric test.
    assert len(skew) == 3
    assert set(skew["test"]) == {"Kruskal-Wallis"}
    assert set(skew["effect_metric"]) == {"rank_biserial"}
    assert skew["effect_value"].apply(np.isfinite).all()
    # The parametric partner (Welch t) is recorded so concordance can be judged.
    assert set(skew["test_partner"]) == {"Welch's t-test"}
    assert skew["concordant"].isin([True, False]).all()


def test_significance_audit_writes_csv_and_emits_describe_record(tmp_path):
    import PyFLASH.report as report

    exp = _overview_dataset(tmp_path)
    report.start()
    try:
        res = pipeline.data_overview(
            exp, by="conditions", include_significance_audit=True,
            run_label="audit_describe", save=True)
        records = report.collect()
    finally:
        if report.is_active():
            report.collect()

    assert os.path.isfile(os.path.join(res["data_dir"], "significance_audit.csv"))
    # Routing the audit through multipleComparisons emits a structured record per
    # marker when the collector is armed -> a non-zero, non-empty describe run.
    assert len(records) > 0
    assert res["n_audit_tests"] > 0


def test_significance_audit_figure_written_and_on_montage(tmp_path):
    # Stage 04: the audit is on by default and renders a status-matrix figure that
    # rides the overview montage.
    exp = _overview_dataset(tmp_path)
    res = pipeline.data_overview(exp, by="conditions", run_label="audit_fig",
                                 save=True)
    assert os.path.isfile(os.path.join(res["fig_dir"], "Significance Audit.svg"))
    montage = res.get("montage")
    assert montage and os.path.isfile(montage)
    # SVG text stays editable per repo convention (svg.fonttype='none').
    svg = open(os.path.join(res["fig_dir"], "Significance Audit.svg"),
               encoding="utf-8").read()
    assert "Significance audit" in svg

    # plot_significance_audit=False suppresses only the figure, not the CSV.
    res2 = pipeline.data_overview(exp, by="conditions",
                                  plot_significance_audit=False,
                                  run_label="audit_nofig", save=True)
    assert not os.path.isfile(
        os.path.join(res2["fig_dir"], "Significance Audit.svg"))
    assert os.path.isfile(os.path.join(res2["data_dir"], "significance_audit.csv"))


def test_sig_audit_matrix_renderer_status_and_columns():
    from PyFLASH.plotting import (
        _ovw_audit_status_frame, _ovw_sig_audit_matrix_figure,
        STATUS_SIG, STATUS_NS,
    )
    df = pd.DataFrame([
        dict(marker="IBA1", contrast="WT vs KO", test="Independent T-Test",
             p=0.003, q=0.01, significant=True, concordant=True, alpha=0.05),
        dict(marker="GFAP", contrast="WT vs KO", test="Mann-Whitney U",
             p=0.07, q=0.20, significant=False, concordant=False, alpha=0.05),
        dict(marker="CK1d", contrast="WT vs KO", test="Kruskal-Wallis",
             p=0.90, q=0.90, significant=False, concordant=True, alpha=0.05),
    ])
    fr = _ovw_audit_status_frame(df, alpha=0.05)
    # worst-first row order (smallest p on top); status codes; annotations.
    assert fr["markers"][0] == "IBA1"
    assert fr["status"][0][0] == STATUS_SIG
    assert fr["status"][2][0] == STATUS_NS
    assert fr["annot"][0][0] == "✱"        # star on significant cell
    assert fr["annot"][1][0] == ".07"           # borderline p label
    assert fr["test_tags"] == ["t", "U", "KW"]
    assert fr["concord"] == ["✓", "⚠", "✓"]  # per-marker concordance
    assert fr["present_codes"] == [STATUS_NS, STATUS_SIG]
    # FDR sidebar summary present because a finite q column exists.
    assert fr["fdr"] and fr["fdr"][0][1] == 1 and fr["fdr"][0][2] == 1

    fig = _ovw_sig_audit_matrix_figure(df, alpha=0.05)
    assert fig is not None
    assert len(fig.axes) == 2                    # main matrix + FDR sidebar
    import matplotlib.pyplot as plt
    plt.close(fig)
    # empty / malformed frames render nothing.
    assert _ovw_sig_audit_matrix_figure(pd.DataFrame()) is None
