"""Tests for the standalone group-comparison plot functions (SuperPlot, effect-size
forest, group-difference matrix) — the figure types group_comparison introduced,
exposed as first-class plots in the plotting module."""

import glob
import os
from types import SimpleNamespace

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd
import pytest

from PyFLASH import plotting
from PyFLASH.spec import PLOT_REGISTRY, _resolve_func, describe_status


def _dataset(tmp_path, with_roi=True):
    rng = np.random.default_rng(3)
    conds = (["WT"] * 8) + (["AD"] * 8)
    n = len(conds)
    animals = [f"S{i:02d}" for i in range(n)]
    a = np.concatenate([rng.normal(10.0, 1.5, 8), rng.normal(14.0, 1.5, 8)])
    b = rng.normal(5.0, 1.0, n)
    summary = pd.DataFrame({
        "AnimalName": animals, "Condition": conds, "Diagnosis": conds,
        "A": a, "B": b,
    })
    fig_path = str(tmp_path / "Python Figures")
    data_path = str(tmp_path / "Data and Stats")
    os.makedirs(fig_path, exist_ok=True)
    os.makedirs(data_path, exist_ok=True)
    exp = SimpleNamespace(
        summary=summary, summaries={"SCN": summary}, fig_path=fig_path,
        data_path=data_path,
        condition_list=[SimpleNamespace(name="WT"), SimpleNamespace(name="AD")],
    )
    if with_roi:
        rows = []
        for an, cond, av in zip(animals, conds, a):
            for r in range(4):
                rows.append({"Region": f"{an}_r{r}", "ROI": "SCN1", "AnimalName": an,
                             "Condition": cond, "A": float(av + rng.normal(0, 0.6))})
        exp.data = {"A_ROI": SimpleNamespace(df=pd.DataFrame(rows).set_index("Region"))}
    return exp


def _svgs(fig_path):
    return glob.glob(os.path.join(fig_path, "**", "*.svg"), recursive=True)


def test_new_plots_registered_and_resolve():
    for name, target in (("superplot", "plot_superplot"),
                         ("effect_forest", "plot_effect_forest"),
                         ("group_matrix", "plot_group_matrix")):
        assert name in PLOT_REGISTRY
        assert _resolve_func(PLOT_REGISTRY[name]).__name__ == target
        assert describe_status(name) == "exempt"


def test_plot_superplot_draws_per_marker(tmp_path):
    exp = _dataset(tmp_path, with_roi=True)
    out = plotting.plot_superplot(exp, filtered_columns=["A"], by="conditions")
    assert isinstance(out, dict) and "A" in out and out["A"] is not None
    files = _svgs(exp.fig_path)
    assert any("SuperPlot" in os.path.basename(f) for f in files)


def test_plot_superplot_skips_markers_without_roi(tmp_path):
    exp = _dataset(tmp_path, with_roi=True)
    # Marker B has no ROI table -> skipped gracefully (not in the output).
    out = plotting.plot_superplot(exp, filtered_columns=["A", "B"], by="conditions")
    assert "A" in out and "B" not in out


def test_plot_superplot_without_any_roi_data_is_empty(tmp_path):
    exp = _dataset(tmp_path, with_roi=False)   # no experiment.data
    out = plotting.plot_superplot(exp, filtered_columns=["A"], by="conditions")
    assert out == {}


def test_plot_effect_forest_draws(tmp_path):
    exp = _dataset(tmp_path)
    fig = plotting.plot_effect_forest(
        exp, filtered_columns=["A", "B"], control="WT", effect_ci=False)
    assert fig is not None
    files = _svgs(exp.fig_path)
    assert any("Effect Size Forest" in os.path.basename(f) for f in files)


def test_plot_group_matrix_draws(tmp_path):
    exp = _dataset(tmp_path)
    fig = plotting.plot_group_matrix(exp, filtered_columns=["A", "B"], control="WT")
    assert fig is not None
    files = _svgs(exp.fig_path)
    assert any("Group Difference Matrix" in os.path.basename(f) for f in files)


def test_effect_forest_factor_grouping(tmp_path):
    exp = _dataset(tmp_path)
    fig = plotting.plot_effect_forest(
        exp, filtered_columns=["A"], factor="Diagnosis", control="WT", effect_ci=False)
    assert fig is not None


def test_roi_resolver_does_not_pool_other_bases():
    from PyFLASH.plotting import _resolve_marker_roi_long
    animals = [f"S{i:02d}" for i in range(6)]
    conds = (["WT"] * 3) + (["AD"] * 3)
    summ = pd.DataFrame({"AnimalName": animals, "Condition": conds, "A": range(6)})
    # Two ROI bases in the experiment; marker A's ROI table holds ONLY OC rows.
    rows = []
    for an, cond in zip(animals, conds):
        for _ in range(3):
            rows.append({"ROI": "OC1", "AnimalName": an, "Condition": cond, "A": 1.0})
    exp = SimpleNamespace(summary=summ, summaries={"SCN": summ, "OC": summ},
                          data={"A_ROI": SimpleNamespace(df=pd.DataFrame(rows))})
    amap = {an: ("WT" if i < 3 else "AD") for i, an in enumerate(animals)}
    # Requesting SCN (absent here) in a multi-base experiment -> no data, must NOT
    # pool the OC rows.
    assert _resolve_marker_roi_long(exp, "A", amap, roi_base="SCN") is None
    # Requesting OC returns the OC rows.
    oc = _resolve_marker_roi_long(exp, "A", amap, roi_base="OC")
    assert oc is not None and len(oc) == 18


def test_unknown_control_raises(tmp_path):
    exp = _dataset(tmp_path)
    with pytest.raises(ValueError):
        plotting.plot_effect_forest(
            exp, filtered_columns=["A"], control="NoSuchGroup", effect_ci=False)
