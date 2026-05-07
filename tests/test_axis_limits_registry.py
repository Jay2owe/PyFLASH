import matplotlib

matplotlib.use("Agg")

import numpy as np
import pandas as pd
import pytest

from types import SimpleNamespace

from PyFLASH import plotting


def _stub_experiment(summary=None):
    if summary is None:
        summary = pd.DataFrame(
            {
                "PeriodMean": [23.2, 23.8, 24.1, 24.7, 25.0],
                "AOEMean": [1.0, 1.5, 2.0, 2.5, 3.0],
                "GFAP_ROI_AreaMean": [4.0, 6.0, 8.0, 10.0, 14.0],
            }
        )
    return SimpleNamespace(summary=summary.copy(), data={})


def test_set_axis_limits_accepts_dict_and_kwargs():
    exp = _stub_experiment()
    plotting.set_axis_limits(exp, {"PeriodMean": (22.0, 26.0)})
    plotting.set_axis_limits(exp, AOEMean=(0.0, 4.0))
    assert exp.axis_limits == {
        "PeriodMean": (22.0, 26.0),
        "AOEMean": (0.0, 4.0),
    }


def test_set_axis_limits_rejects_bad_pairs():
    exp = _stub_experiment()
    with pytest.raises(ValueError):
        plotting.set_axis_limits(exp, {"PeriodMean": (22.0, 22.0)})
    with pytest.raises(ValueError):
        plotting.set_axis_limits(exp, {"PeriodMean": (float("inf"), 1.0)})


def test_set_axis_limits_none_clears_single_key():
    exp = _stub_experiment()
    plotting.set_axis_limits(exp, {"PeriodMean": (22.0, 26.0)})
    plotting.set_axis_limits(exp, {"PeriodMean": None})
    assert "PeriodMean" not in exp.axis_limits


def test_clear_axis_limits_all_and_subset():
    exp = _stub_experiment()
    plotting.set_axis_limits(exp, {"PeriodMean": (22.0, 26.0), "AOEMean": (0.0, 4.0)})
    plotting.clear_axis_limits(exp, "PeriodMean")
    assert "PeriodMean" not in exp.axis_limits
    assert "AOEMean" in exp.axis_limits
    plotting.clear_axis_limits(exp)
    assert exp.axis_limits == {}


def test_lock_axis_limits_populates_from_summary():
    exp = _stub_experiment()
    result = plotting.lock_axis_limits(exp, columns=["PeriodMean"])
    assert result["PeriodMean"] == (23.2, 25.0)
    assert exp.axis_limits["PeriodMean"] == (23.2, 25.0)


def test_lock_axis_limits_does_not_overwrite_by_default():
    exp = _stub_experiment()
    plotting.set_axis_limits(exp, {"PeriodMean": (0.0, 100.0)})
    plotting.lock_axis_limits(exp, columns=["PeriodMean"])
    assert exp.axis_limits["PeriodMean"] == (0.0, 100.0)
    plotting.lock_axis_limits(exp, columns=["PeriodMean"], overwrite=True)
    assert exp.axis_limits["PeriodMean"] == (23.2, 25.0)


def test_lookup_axis_registry_returns_none_for_missing():
    exp = _stub_experiment()
    assert plotting._lookup_axis_registry(exp, "DoesNotExist") is None
    assert plotting._lookup_axis_registry(None, "Anything") is None


def test_resolve_effective_axis_range_prefers_explicit():
    exp = _stub_experiment()
    plotting.set_axis_limits(exp, {"PeriodMean": (22.0, 26.0)})
    assert plotting._resolve_effective_axis_range(
        exp, "PeriodMean", (10.0, 15.0)
    ) == (10.0, 15.0)
    assert plotting._resolve_effective_axis_range(
        exp, "PeriodMean", None
    ) == (22.0, 26.0)


def test_plot_histograms_partial_xmin_xmax_fills_from_data(monkeypatch):
    from PyFLASH.conditions import condition, conditionList

    class _FakeMarker:
        def __init__(self, df):
            self.df = df

    marker_df = pd.DataFrame(
        {
            "AnimalName": ["S1"] * 4 + ["A1"] * 4,
            "Condition": ["Syn"] * 4 + ["APP"] * 4,
            "CK1d_Val": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
        }
    )
    summary = pd.DataFrame(
        [
            {"AnimalName": "S1", "Condition": "Syn"},
            {"AnimalName": "A1", "Condition": "APP"},
        ]
    )
    conds = conditionList(
        [
            condition("Syn", "Syn", "#111111", "Genotype"),
            condition("APP", "APP", "#222222", "Genotype"),
        ]
    )
    exp = SimpleNamespace(
        summary=summary,
        summaries={"SCN": summary.copy()},
        data={"CK1d": _FakeMarker(marker_df.set_index(["AnimalName", "Condition"]))},
        condition_list=conds,
        factorDict=conds.factorDict,
        fig_path=".",
    )

    seen = []

    def _recording(ctx, state, **kwargs):
        seen.append((kwargs.get("bin_range"), kwargs.get("bins_spec")))
        return {"group": ctx.condition}

    monkeypatch.setattr(plotting, "histogram_action", _recording)
    monkeypatch.setattr(plotting, "_resolve_marker_data_key", lambda exp, m: m)
    monkeypatch.setattr(plotting, "_resolve_histogram_x_column", lambda exp, m, a: "CK1d_Val")

    # Partial xmin only — xmax must be filled from data (8.0).
    plotting.plot_histograms(
        exp,
        marker="CK1d",
        x_attr="Val",
        xmin=2.0,
        save=False,
    )
    assert seen, "histogram_action was not invoked"
    assert seen[0][0] == (2.0, 8.0)

    seen.clear()

    # Registry-supplied partial bound (None, 6.0) — lo must come from data min.
    plotting.set_axis_limits(exp, {"CK1d_Val": (None, 6.0)})
    plotting.plot_histograms(
        exp,
        marker="CK1d",
        x_attr="Val",
        save=False,
    )
    assert seen[0][0] == (1.0, 6.0)


def test_compute_queue_shared_ranges_skips_flat_and_missing_columns():
    df = pd.DataFrame(
        {
            "varies": [1.0, 2.0, 3.0],
            "flat": [5.0, 5.0, 5.0],
            "missing_in_index": [np.nan, np.nan, np.nan],
        }
    )
    result = plotting._compute_queue_shared_ranges(
        df, ["varies", "flat", "missing_in_index", "absent"]
    )
    assert result == {"varies": (1.0, 3.0)}
