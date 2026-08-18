"""Shared per-column display-label override (`column_labels`).

Covers the core mechanism (utils helpers + get_display_name hook + run()
integration) and adoption on representative plots: a run()-based plot, a
decorated non-run plot, and the directly-wrapped plot_correlation_contrast.
"""
import matplotlib

matplotlib.use("Agg")

import numpy as np
import pandas as pd
import pytest

from PyFLASH import ConditionBuilder, from_dataframe
from PyFLASH.iteration import run
import PyFLASH.plotting as P
from PyFLASH.plotting import get_display_name
from PyFLASH.utils import (
    active_column_label, column_label_overrides, normalize_column_labels,
    resolve_column_labels,
)


# ── core helpers ─────────────────────────────────────────────────────────────

def test_normalize_dict_and_list_and_none():
    assert normalize_column_labels(None, None) == {}
    assert normalize_column_labels(["a", "b"], {"a": "Aye"}) == {"a": "Aye"}
    assert normalize_column_labels(["a", "b"], ["Aye", "Bee"]) == {"a": "Aye", "b": "Bee"}


def test_normalize_list_length_mismatch_raises():
    with pytest.raises(ValueError):
        normalize_column_labels(["a", "b", "c"], ["only", "two"])


def test_resolve_fills_fallback_via_display():
    out = resolve_column_labels(["a", "b"], {"a": "Aye"}, display=lambda c: f"<{c}>")
    assert out == {"a": "Aye", "b": "<b>"}


def test_context_pushes_and_pops():
    assert active_column_label("M1") is None
    with column_label_overrides({"M1": "Marker One"}):
        assert active_column_label("M1") == "Marker One"
        assert get_display_name("M1") == "Marker One"
        # nested shadowing
        with column_label_overrides({"M1": "Inner"}):
            assert get_display_name("M1") == "Inner"
        assert get_display_name("M1") == "Marker One"
    assert active_column_label("M1") is None


def test_override_wins_over_house_map_and_ignores_minimal():
    # A column the house map would rewrite is overridden verbatim.
    with column_label_overrides({"Totalcounts": "TOTAL"}):
        assert get_display_name("Totalcounts") == "TOTAL"
        assert get_display_name("Totalcounts", minimal=True) == "TOTAL"


def test_expN_suffix_key_matches():
    with column_label_overrides({"GFAP_Count": "Astro"}):
        assert get_display_name("GFAP_Count.exp1") == "Astro"


def test_empty_override_is_noop():
    with column_label_overrides(normalize_column_labels(None, None)):
        assert get_display_name("M1") == "M1"


# ── plot fixtures ────────────────────────────────────────────────────────────

def _exp(tmp_path):
    rng = np.random.default_rng(1)
    rows = []
    for grp in ("Control", "AD"):
        for i in range(8):
            rows.append({"Subject": f"{grp}{i}", "Diagnosis": grp,
                         "M1": float(rng.normal(5, 1)), "M2": float(rng.normal(3, 1))})
    df = pd.DataFrame(rows)
    cond = ConditionBuilder("Diagnosis").add("Control").add("AD").build()
    return from_dataframe(df, conditions=cond, name="t", condition_col="Diagnosis",
                          animal_col="Subject", fig_path=tmp_path / "f", data_path=tmp_path / "d")


def _fig_text(fig):
    out = []
    for ax in fig.axes:
        out += [t.get_text() for t in ax.texts]
        out += [ax.get_title(), ax.get_xlabel(), ax.get_ylabel()]
        out += [t.get_text() for t in ax.get_xticklabels()]
        out += [t.get_text() for t in ax.get_yticklabels()]
        leg = ax.get_legend()
        if leg:
            out += [t.get_text() for t in leg.get_texts()]
    return [t for t in out if t]


def test_run_harness_activates_override(tmp_path):
    exp = _exp(tmp_path)

    def act(ctx, state):
        return {"lbl": get_display_name("M1")}

    res = run(exp, over="conditions", action=act, column_labels={"M1": "Marker One"})
    assert all(v == "Marker One" for v in res["lbl"])
    assert get_display_name("M1") == "M1"  # popped after run


def test_decorated_plot_group_matrix_remaps(tmp_path):
    exp = _exp(tmp_path)
    fig = P.plot_group_matrix(exp, data_cols=["M1", "M2"], factor="Diagnosis",
                              control="Control", column_labels={"M1": "Marker One"},
                              save=False)
    figs = [fig] if hasattr(fig, "axes") else list(fig.values())
    texts = [t for f in figs for t in _fig_text(f)]
    assert any("Marker One" in t for t in texts)


def test_correlation_contrast_dict_and_list(tmp_path):
    exp = _exp(tmp_path)
    fig = P.plot_correlation_contrast(exp, x="M1", y=["M2"], factor="Diagnosis",
                                      reference="Control",
                                      column_labels={"M2": "Measure Two"}, save=False)
    labels = [t.get_text() for t in fig.axes[0].get_legend().get_texts()]
    assert "Measure Two" in labels
    # positional list form
    fig2 = P.plot_correlation_contrast(exp, x="M1", y=["M2"], factor="Diagnosis",
                                       reference="Control",
                                       column_labels=["Listed"], save=False)
    labels2 = [t.get_text() for t in fig2.axes[0].get_legend().get_texts()]
    assert "Listed" in labels2
