"""Tests for the group_comparison pipeline (inferential marker comparison)."""

import os
from types import SimpleNamespace

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd
import pytest

from PyFLASH import pipeline
from PyFLASH.spec import (
    DESCRIBE_COVERED, DESCRIBE_EXEMPT, DESCRIBE_UNREVIEWED, PLOT_REGISTRY,
    _resolve_func, describe_status,
)
from PyFLASH.stats import runOWA


def _gc_dataset(tmp_path, n_per=12, with_roi=False):
    """WT/AD design: marker A is strongly higher in AD; marker B has no effect."""
    rng = np.random.default_rng(11)
    conditions = (["WT"] * n_per) + (["AD"] * n_per)
    n = len(conditions)
    animals = [f"S{i:02d}" for i in range(n)]
    a = np.concatenate([rng.normal(10.0, 1.5, n_per), rng.normal(15.0, 1.5, n_per)])
    b = rng.normal(5.0, 1.0, n)
    sex = np.where(np.arange(n) % 2 == 0, "F", "M")

    summary = pd.DataFrame({
        "AnimalName": animals,
        "Condition": conditions,
        "Diagnosis": conditions,
        "Sex": sex,
        "A": a,
        "B": b,
    })
    fig_path = str(tmp_path / "Python Figures")
    data_path = str(tmp_path / "Data and Stats")
    os.makedirs(fig_path, exist_ok=True)
    os.makedirs(data_path, exist_ok=True)
    exp = SimpleNamespace(
        summary=summary,
        summaries={"SCN": summary},
        fig_path=fig_path,
        data_path=data_path,
        condition_list=[SimpleNamespace(name="WT"), SimpleNamespace(name="AD")],
    )
    if with_roi:
        # ROI-level rows for marker A only (4 ROIs/animal). Marker B has no ROI
        # data, so a nested engine must fall back to animal-mean for B.
        rows = []
        for an, cond, aval in zip(animals, conditions, a):
            for r in range(4):
                rows.append({
                    "Region": f"{an}_r{r}",
                    "AnimalName": an,
                    "Condition": cond,
                    "A": float(aval + rng.normal(0.0, 0.8)),
                })
        roi_df = pd.DataFrame(rows).set_index("Region")
        exp.data = {"A_ROI": SimpleNamespace(df=roi_df)}
    return exp


def test_registry_alias_resolves_and_is_describe_covered():
    assert "group_comparison_pipeline" in PLOT_REGISTRY
    func = _resolve_func(PLOT_REGISTRY["group_comparison_pipeline"])
    assert func is pipeline.group_comparison
    # Classified for the describe layer, in exactly one set.
    assert describe_status("group_comparison_pipeline") == "covered"
    in_sets = sum("group_comparison_pipeline" in s
                  for s in (DESCRIBE_COVERED, DESCRIBE_EXEMPT, DESCRIBE_UNREVIEWED))
    assert in_sets == 1


def test_group_comparison_detects_planted_difference(tmp_path):
    exp = _gc_dataset(tmp_path)

    res = pipeline.group_comparison(exp, control="WT", run_label="gc_basic", save=True)

    assert res["pipeline"] == "group_comparison"
    rt = res["results_table"]
    assert set(rt["marker"]) == {"A", "B"}
    assert set(rt["comparison"]) == {"AD vs WT"}

    a_row = rt[rt["marker"] == "A"].iloc[0]
    assert a_row["p"] < 0.05                 # strong planted effect
    assert a_row["hedges_g"] > 1.0           # AD much higher than WT
    assert a_row["reference"] == "WT" and a_row["group"] == "AD"
    b_row = rt[rt["marker"] == "B"].iloc[0]
    assert b_row["p"] > 0.05                 # no effect

    # No cross-marker q by default — different markers are not a family.
    assert res["has_q"] is False
    assert "q" not in rt.columns

    data_dir = res["data_dir"]
    fig_dir = res["fig_dir"]
    assert data_dir == fig_dir
    for fname in ("group_comparison_results.csv", "omnibus.csv", "manifest.json"):
        assert os.path.isfile(os.path.join(data_dir, fname)), fname
    assert os.path.isfile(os.path.join(fig_dir, "Effect Size Forest p.svg"))
    assert os.path.isfile(os.path.join(fig_dir, "Stats Matrix p.svg"))
    assert os.path.isfile(os.path.join(fig_dir, "Volcano", "Volcano AD vs WT p.svg"))
    # One overview montage spanning the run's headline figures.
    assert res.get("montage") and os.path.isfile(res["montage"])


def test_default_all_pairs_without_control(tmp_path):
    exp = _gc_dataset(tmp_path)
    res = pipeline.group_comparison(exp, run_label="gc_allpairs", save=False)
    rt = res["results_table"]
    # One contrast between the two conditions, regardless of reference direction.
    comps = set(rt["comparison"])
    assert comps in ({"AD vs WT"}, {"WT vs AD"})


def test_group_comparison_uses_selected_parametric_posthoc(tmp_path):
    rng = np.random.default_rng(0)
    labels = ["WT", "MCI", "AD"]
    rows = []
    grouped = []
    for label, mean in zip(labels, [-0.2, 0.0, 0.2]):
        values = rng.normal(mean, 1.0, 20)
        grouped.append(pd.Series(values))
        for idx, value in enumerate(values):
            rows.append({
                "AnimalName": f"{label}{idx:02d}",
                "Condition": label,
                "A": float(value),
            })
    summary = pd.DataFrame(rows)
    exp = SimpleNamespace(
        summary=summary,
        summaries={"SCN": summary},
        fig_path=str(tmp_path / "Python Figures"),
        data_path=str(tmp_path / "Data and Stats"),
        condition_list=[SimpleNamespace(name=label) for label in labels],
    )
    os.makedirs(exp.fig_path, exist_ok=True)
    os.makedirs(exp.data_path, exist_ok=True)
    comparisons = ["1-2", "1-3", "2-3"]

    res = pipeline.group_comparison(
        exp,
        data_cols=["A"],
        comparisons=comparisons,
        posthoc="Holm-Sidak",
        save=False,
        plot_bars=False,
        plot_forest=False,
        plot_volcano=False,
        plot_stats_matrix=False,
    )
    expected, _, _, expected_dict, expected_posthoc = runOWA(
        grouped,
        comparisons,
        {},
        posthoc="Holm-Sidak",
    )

    assert expected_posthoc == "Holm-Sidak"
    assert expected == expected_dict["Holm-Sidak"][1]
    rt = res["results_table"].sort_values("comparison").reset_index(drop=True)
    assert res["tests"] == ["One-Way ANOVA"]
    assert len(rt) == len(comparisons)
    assert rt["p"].tolist() == pytest.approx(
        pd.DataFrame({
            "comparison": ["MCI vs WT", "AD vs WT", "AD vs MCI"],
            "p": expected,
        }).sort_values("comparison")["p"].tolist()
    )


def test_screen_mode_adds_q_but_keeps_p(tmp_path):
    exp = _gc_dataset(tmp_path)

    res = pipeline.group_comparison(
        exp, control="WT", screen=True, run_label="gc_screen", save=True)

    rt = res["results_table"]
    assert res["has_q"] is True
    assert "q" in rt.columns and "p" in rt.columns   # invariant: p always present
    assert rt["p"].notna().any()
    fig_dir = res["fig_dir"]
    assert res["data_dir"] == fig_dir
    # Every q figure has a p counterpart.
    assert os.path.isfile(os.path.join(fig_dir, "Effect Size Forest p.svg"))
    assert os.path.isfile(os.path.join(fig_dir, "Effect Size Forest q.svg"))
    assert os.path.isfile(os.path.join(fig_dir, "Stats Matrix p.svg"))
    assert os.path.isfile(os.path.join(fig_dir, "Stats Matrix q.svg"))


def test_gate_fdr_requires_screen(tmp_path):
    exp = _gc_dataset(tmp_path)
    with pytest.raises(ValueError):
        pipeline.group_comparison(exp, gate="fdr", run_label="gc_bad", save=False)


def test_min_n_skips_markers(tmp_path):
    exp = _gc_dataset(tmp_path)
    res = pipeline.group_comparison(
        exp, control="WT", min_n=50, run_label="gc_skip", save=False)
    assert res["n_tests"] == 0
    assert res["n_skipped_markers"] == 2
    assert res["results_table"].empty


def test_invalid_engine_and_too_few_groups(tmp_path):
    exp = _gc_dataset(tmp_path)
    with pytest.raises(ValueError):
        pipeline.group_comparison(exp, engine="nope", save=False)
    # specificity that leaves a single condition -> cannot compare.
    with pytest.raises(ValueError):
        pipeline.group_comparison(
            exp, specificity=("Diagnosis", "AD"), run_label="gc_one", save=False)


def test_mixed_engine_falls_back_without_roi_data(tmp_path):
    exp = _gc_dataset(tmp_path)            # no experiment.data
    res = pipeline.group_comparison(
        exp, engine="mixed", control="WT", run_label="gc_mixed_fb", save=False)
    assert res["n_fallback_markers"] == 2
    rt = res["results_table"]
    assert rt["engine"].eq("auto").all()
    assert rt["test"].str.contains("fallback").all()


def test_mixed_engine_uses_roi_data_when_present(tmp_path):
    exp = _gc_dataset(tmp_path, with_roi=True)
    res = pipeline.group_comparison(
        exp, engine="mixed", control="WT", run_label="gc_mixed",
        plot_superplots=True, save=True)
    rt = res["results_table"]
    a_row = rt[rt["marker"] == "A"].iloc[0]
    assert a_row["engine"] == "mixed"
    assert np.isfinite(a_row["icc"])
    assert a_row["p"] < 0.05
    # Marker B has no ROI data -> per-marker fallback to the animal-mean test.
    b_row = rt[rt["marker"] == "B"].iloc[0]
    assert b_row["engine"] == "auto"
    assert res["n_fallback_markers"] == 1
    # SuperPlot drawn for the ROI-backed marker.
    assert os.path.isfile(os.path.join(res["fig_dir"], "SuperPlots", "SuperPlot A.svg"))


def _gc_multibase_dataset(tmp_path, n_per=12):
    """ROI rows in two bases: SCN has AD>WT (+5), OC has AD<WT (-5). The animal
    summary is the SCN aggregate. If a nested engine fails to scope to the SCN
    base, the opposing OC rows cancel the effect."""
    rng = np.random.default_rng(5)
    conds = (["WT"] * n_per) + (["AD"] * n_per)
    n = len(conds)
    animals = [f"S{i:02d}" for i in range(n)]
    # Per-animal means with genuine between-animal variation (so the mixed model's
    # random intercept is estimable), AD higher in SCN and lower in OC.
    scn_mean = np.array([10.0] * n_per + [15.0] * n_per) + rng.normal(0, 1.2, n)
    oc_mean = np.array([10.0] * n_per + [5.0] * n_per) + rng.normal(0, 1.2, n)
    rows = []
    for an, cond, sm, om in zip(animals, conds, scn_mean, oc_mean):
        for _ in range(4):
            rows.append({"ROI": "SCN1", "Region": "SCN1", "AnimalName": an,
                         "Condition": cond, "A": float(sm + rng.normal(0, 0.6))})
        for _ in range(4):
            rows.append({"ROI": "OC1", "Region": "OC1", "AnimalName": an,
                         "Condition": cond, "A": float(om + rng.normal(0, 0.6))})
    roi_df = pd.DataFrame(rows)
    summary_scn = pd.DataFrame({"AnimalName": animals, "Condition": conds, "A": scn_mean})
    fig_path = str(tmp_path / "Python Figures")
    data_path = str(tmp_path / "Data and Stats")
    os.makedirs(fig_path, exist_ok=True)
    os.makedirs(data_path, exist_ok=True)
    return SimpleNamespace(
        summary=summary_scn, summaries={"SCN": summary_scn},
        fig_path=fig_path, data_path=data_path,
        condition_list=[SimpleNamespace(name="WT"), SimpleNamespace(name="AD")],
        data={"A_ROI": SimpleNamespace(df=roi_df)},
    )


def test_mixed_engine_scopes_nested_data_to_roi_base(tmp_path):
    exp = _gc_multibase_dataset(tmp_path)
    res = pipeline.group_comparison(
        exp, engine="mixed", control="WT", roi="SCN", run_label="gc_base", save=False)
    a = res["results_table"]
    a_row = a[a["marker"] == "A"].iloc[0]
    assert a_row["engine"] == "mixed"
    # Only the SCN ROI rows are tested; leaking the opposing OC rows would cancel
    # the effect and the mixed p would not be significant.
    assert a_row["p"] < 0.05


def test_bootstrap_engine_with_roi_data(tmp_path):
    exp = _gc_dataset(tmp_path, with_roi=True)
    res = pipeline.group_comparison(
        exp, engine="bootstrap", control="WT", n_boot=500, random_state=0,
        run_label="gc_boot", save=False)
    rt = res["results_table"]
    a_row = rt[rt["marker"] == "A"].iloc[0]
    assert a_row["engine"] == "bootstrap"
    assert a_row["p"] < 0.05


def test_specificity_queue_merges_into_one_folder(tmp_path):
    # Compare WT vs AD within each sex, merged into one run folder.
    exp = _gc_dataset(tmp_path)
    res = pipeline.group_comparison(
        exp,
        specificity=[("Sex", "F"), ("Sex", "M")],
        control="WT",
        run_label="gc_queue",
        save=True,
    )
    assert res["pipeline"] == "group_comparison"
    assert os.path.basename(res["data_dir"]) == "gc_queue"
    assert os.path.isfile(os.path.join(res["data_dir"], "manifest.json"))
    assert {tuple(c["specificity"]) for c in res["conditions"]} == {
        ("Sex", "F"), ("Sex", "M")}
    assert res.get("montage") and os.path.isfile(res["montage"])


def test_group_descriptives_written_and_constant_marker_skipped(tmp_path):
    exp = _gc_dataset(tmp_path)
    exp.summary["Const"] = 5.0   # zero-variance marker must be skipped, not NaN rows
    res = pipeline.group_comparison(exp, control="WT", run_label="gc_desc", save=True)

    # Per marker x group descriptives are written.
    assert os.path.isfile(os.path.join(res["data_dir"], "group_descriptives.csv"))
    desc = res["descriptives"]
    assert set(desc["group"]) == {"WT", "AD"}
    assert {"A", "B", "Const"}.issubset(set(desc["marker"]))

    # The constant marker is skip-recorded, never emitted as a NaN result row.
    assert "Const" not in set(res["results_table"]["marker"])
    assert "Const" in set(res["skipped"]["marker"])


def test_factor_grouping_compares_factor_levels(tmp_path):
    exp = _gc_dataset(tmp_path)
    res = pipeline.group_comparison(
        exp, factor="Diagnosis", control="WT", run_label="gc_factor", save=False)
    rt = res["results_table"]
    assert set(rt["comparison"]) == {"AD vs WT"}
    assert rt[rt["marker"] == "A"].iloc[0]["p"] < 0.05


def test_factor_grouping_ignores_mismatched_condition_comparisons(tmp_path):
    # A condition_list whose default comparison tokens index 4 crossed conditions
    # must NOT be inherited when grouping by a 2-level factor (they would mis-map
    # or resolve to nothing and raise). The factor run should fall through to the
    # control-vs-each default over the factor levels.
    exp = _gc_dataset(tmp_path)
    exp.condition_list = SimpleNamespace(comparisons=["1-3", "2-4"])
    res = pipeline.group_comparison(
        exp, factor="Diagnosis", control="WT", run_label="gc_fc", save=False)
    assert set(res["results_table"]["comparison"]) == {"AD vs WT"}


def test_auto_slug_varies_with_engine_and_screen(tmp_path):
    exp = _gc_dataset(tmp_path)
    r1 = pipeline.group_comparison(exp, control="WT", save=False)
    r2 = pipeline.group_comparison(exp, control="WT", screen=True, save=False)
    assert r1["run_label"] != r2["run_label"]
