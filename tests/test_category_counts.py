import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
import pytest

from PyFLASH import ConditionBuilder, from_dataframe
from PyFLASH.plotting import plot_category_counts


def _season_experiment(tmp_path):
    """Control (n=6) and AD (n=4) with a known season + site distribution."""
    df = pd.DataFrame({
        "Subject ID": ["C1", "C2", "C3", "C4", "C5", "C6", "A1", "A2", "A3", "A4"],
        "Diagnosis": ["Control"] * 6 + ["AD"] * 4,
        "season": ["Winter", "Winter", "Spring", "Spring", "Summer", "Autumn",
                   "Winter", "Spring", "Autumn", "Autumn"],
        "Site": ["S1", "S2", "S1", "S2", "S1", "S2", "S1", "S2", "S1", "S2"],
        "Marker A": [1.0] * 10,
    })
    conditions = (
        ConditionBuilder("Diagnosis")
        .add("Control", short="Control", color="grey")
        .add("AD", short="AD", color="red")
        .compare("Control", "AD")
        .build()
    )
    exp = from_dataframe(
        df,
        conditions=conditions,
        name="season-table",
        condition_col="Diagnosis",
        animal_col="Subject ID",
        fig_path=tmp_path / "figures",
        data_path=tmp_path / "data",
    )
    return exp


ORDER = ["Winter", "Spring", "Summer", "Autumn"]
# group order is [Control, AD]; heights per season across those two groups
EXPECTED = {
    "Winter": [2.0, 1.0],
    "Spring": [2.0, 1.0],
    "Summer": [1.0, 0.0],
    "Autumn": [1.0, 2.0],
}


def _heights_by_level(fig, order):
    """Map each category level to its per-group bar heights (group order)."""
    conts = fig.axes[0].containers
    return {lvl: [p.get_height() for p in cont] for lvl, cont in zip(order, conts)}


def test_grouped_counts_by_conditions(tmp_path):
    exp = _season_experiment(tmp_path)
    assert "season" in exp.summary.columns
    fig = plot_category_counts(exp, "season", category_order=ORDER, save=False)
    assert _heights_by_level(fig, ORDER) == EXPECTED
    plt.close(fig)


def test_factor_grouping_matches_conditions(tmp_path):
    exp = _season_experiment(tmp_path)
    fig = plot_category_counts(exp, "season", factor="Diagnosis",
                               category_order=ORDER, save=False)
    # Factor grouping over Diagnosis yields the same [Control, AD] groups here.
    assert _heights_by_level(fig, ORDER) == EXPECTED
    plt.close(fig)


def test_normalize_sums_to_100_per_group(tmp_path):
    exp = _season_experiment(tmp_path)
    fig = plot_category_counts(exp, "season", category_order=ORDER,
                               normalize=True, save=False)
    heights = _heights_by_level(fig, ORDER)
    control_total = sum(heights[lvl][0] for lvl in ORDER)
    ad_total = sum(heights[lvl][1] for lvl in ORDER)
    assert control_total == pytest.approx(100.0)
    assert ad_total == pytest.approx(100.0)
    assert heights["Winter"][0] == pytest.approx(2 / 6 * 100)
    plt.close(fig)


def test_stacked_returns_figure_with_expected_heights(tmp_path):
    exp = _season_experiment(tmp_path)
    fig = plot_category_counts(exp, "season", kind="stacked",
                               category_order=ORDER, save=False)
    assert _heights_by_level(fig, ORDER) == EXPECTED
    plt.close(fig)


def test_category_order_and_labels(tmp_path):
    exp = _season_experiment(tmp_path)
    labels = {"Winter": "Wtr", "Spring": "Spr", "Summer": "Smr", "Autumn": "Aut"}
    fig = plot_category_counts(exp, "season", category_order=ORDER,
                               category_labels=labels, save=False)
    legend_texts = [t.get_text() for t in fig.axes[0].get_legend().get_texts()]
    assert legend_texts == ["Wtr", "Spr", "Smr", "Aut"]
    plt.close(fig)


def test_missing_category_raises(tmp_path):
    exp = _season_experiment(tmp_path)
    with pytest.raises(ValueError):
        plot_category_counts(exp, "not_a_column", save=False)


def test_invalid_kind_raises(tmp_path):
    exp = _season_experiment(tmp_path)
    with pytest.raises(ValueError):
        plot_category_counts(exp, "season", kind="pie", save=False)


def test_specificity_queue_returns_dict(tmp_path):
    exp = _season_experiment(tmp_path)
    out = plot_category_counts(
        exp, "season", category_order=ORDER,
        specificity=[("Site", "S1"), ("Site", "S2")], save=False,
    )
    assert isinstance(out, dict)
    assert set(out) == {("Site", "S1"), ("Site", "S2")}
    for fig in out.values():
        plt.close(fig)


def test_category_list_queue_returns_dict(tmp_path):
    exp = _season_experiment(tmp_path)
    out = plot_category_counts(exp, ["season"], category_order=ORDER, save=False)
    assert isinstance(out, dict)
    assert set(out) == {"season"}
    plt.close(out["season"])
