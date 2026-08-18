import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
import pytest
from types import SimpleNamespace
from statsmodels.stats.multitest import multipletests

from PyFLASH.stats import (
    STATS_ANNOTATION_X,
    STATS_ANNOTATION_Y,
    _annotate_stats_error,
    _annotate_stats_summary,
    multipleComparisons,
    plot_comparison_lines_from_figdata,
    runITTest,
    runKW,
    runOWA,
)


class _Condition:
    def __init__(self, name):
        self.name = name


def test_stats_summary_annotation_uses_right_offset_anchor():
    fig, ax = plt.subplots()
    try:
        _annotate_stats_summary(
            ax=ax,
            test="One-Way ANOVA",
            post_hoc="Tukey",
            overall=(None, 0.01),
            comparisons=["1-2"],
            pairwise_pvalues=[0.04],
            condition_list=[_Condition("AD"), _Condition("Control")],
            effect_strings=["Effect sizes:", "AD vs Control: g=-1.0"],
        )

        text = ax.texts[-1]
        assert text.get_position() == (STATS_ANNOTATION_X, STATS_ANNOTATION_Y)
        assert text.get_ha() == "left"
        assert text.get_va() == "top"
        assert STATS_ANNOTATION_X > 1.02
    finally:
        plt.close(fig)


def test_stats_error_annotation_uses_same_right_offset_anchor():
    fig, ax = plt.subplots()
    try:
        _annotate_stats_error(ax, "example")

        text = ax.texts[-1]
        assert text.get_position() == (STATS_ANNOTATION_X, STATS_ANNOTATION_Y)
        assert text.get_ha() == "left"
        assert text.get_va() == "top"
    finally:
        plt.close(fig)


def test_run_kw_can_select_dunn_bonferroni():
    groups = [
        pd.Series([1.0, 1.2, 1.1, 1.3]),
        pd.Series([2.0, 2.1, 2.2, 2.3]),
        pd.Series([4.0, 4.2, 4.1, 4.3]),
    ]
    comparisons = ["1-2", "1-3", "2-3"]

    results, _, _, results_dict, posthoc = runKW(
        groups,
        comparisons,
        {},
        posthoc="Dunn",
        posthoc_correction="Bonferroni",
    )

    assert posthoc == "Dunn Bonferroni"
    assert results == results_dict["Dunn-Bonferroni"][1]
    assert results != results_dict["Conover-Uncorrected"][1]


@pytest.mark.parametrize(
    ("requested", "label", "method"),
    [
        ("Holm-Bonferroni", "Holm", "holm"),
        ("Sidak", "Sidak", "sidak"),
        ("Benjamini-Hochberg", "FDR-BH", "fdr_bh"),
        ("two-stage BH", "FDR-TSBH", "fdr_tsbh"),
    ],
)
def test_run_kw_accepts_additional_posthoc_corrections(requested, label, method):
    groups = [
        pd.Series([1.0, 1.2, 1.1, 1.3]),
        pd.Series([2.0, 2.1, 2.2, 2.3]),
        pd.Series([4.0, 4.2, 4.1, 4.3]),
    ]
    comparisons = ["1-2", "1-3", "2-3"]

    results, _, _, results_dict, posthoc = runKW(
        groups,
        comparisons,
        {},
        posthoc="Dunn",
        posthoc_correction=requested,
    )

    expected = multipletests(results_dict["Dunn-Uncorrected"][1], method=method)[1]
    assert posthoc == f"Dunn {label}"
    assert results_dict[f"Dunn-{label}"][1] == pytest.approx(expected)
    assert results == pytest.approx(expected)


@pytest.mark.parametrize("requested", ["raw", "unadjusted", "off", "0"])
def test_run_kw_accepts_uncorrected_posthoc_correction_aliases(requested):
    groups = [
        pd.Series([1.0, 1.2, 1.1, 1.3]),
        pd.Series([2.0, 2.1, 2.2, 2.3]),
        pd.Series([4.0, 4.2, 4.1, 4.3]),
    ]
    comparisons = ["1-2", "1-3", "2-3"]

    results, _, _, results_dict, posthoc = runKW(
        groups,
        comparisons,
        {},
        posthoc="Dunn",
        posthoc_correction=requested,
    )

    assert posthoc == "Dunn Uncorrected"
    assert results == results_dict["Dunn-Uncorrected"][1]


@pytest.mark.parametrize(
    ("requested", "label"),
    [
        ("Nemenyi", "Nemenyi"),
        ("Dwass-Steel-Critchlow-Fligner", "DSCF"),
    ],
)
def test_run_kw_accepts_additional_nonparametric_posthoc_tests(requested, label):
    groups = [
        pd.Series([1.0, 1.2, 1.1, 1.3]),
        pd.Series([2.0, 2.1, 2.2, 2.3]),
        pd.Series([4.0, 4.2, 4.1, 4.3]),
    ]
    comparisons = ["1-2", "1-3", "2-3"]

    results, _, _, results_dict, posthoc = runKW(
        groups,
        comparisons,
        {},
        posthoc=requested,
        posthoc_correction="Bonferroni",
    )

    assert posthoc == label
    assert results == results_dict[label][1]
    assert len(results) == len(comparisons)


def test_run_owa_accepts_holm_sidak_posthoc():
    groups = [
        pd.Series([1.0, 1.1, 1.2, 1.3]),
        pd.Series([2.0, 2.1, 2.2, 2.3]),
        pd.Series([4.0, 4.1, 4.2, 4.3]),
    ]
    comparisons = ["1-2", "1-3", "2-3"]

    raw, _, _, _, raw_posthoc = runOWA(
        groups,
        comparisons,
        {},
        posthoc="Fisher LSD",
        posthoc_correction="Uncorrected",
    )
    results, _, _, results_dict, posthoc = runOWA(
        groups,
        comparisons,
        {},
        posthoc="Holm-Sidak",
    )

    expected = multipletests(raw, method="holm-sidak")[1]
    assert raw_posthoc == "Fisher LSD"
    assert posthoc == "Holm-Sidak"
    assert results_dict["Holm-Sidak"][1] == pytest.approx(expected)
    assert results == pytest.approx(expected)


def test_run_owa_accepts_dunnett_control_comparisons():
    groups = [
        pd.Series([1.0, 1.1, 1.2, 1.3]),
        pd.Series([2.0, 2.1, 2.2, 2.3]),
        pd.Series([4.0, 4.1, 4.2, 4.3]),
    ]
    comparisons = ["1-2", "1-3"]

    results, _, _, results_dict, posthoc = runOWA(
        groups,
        comparisons,
        {},
        posthoc="Dunnett",
    )

    assert posthoc == "Dunnett"
    assert results == results_dict["Dunnett"][1]
    assert len(results) == len(comparisons)
    assert results[1] < results[0]


@pytest.mark.parametrize(
    ("requested", "label"),
    [
        ("Scheffe", "Scheffe"),
        ("Tamhane T2", "Tamhane T2"),
    ],
)
def test_run_owa_accepts_additional_parametric_matrix_posthoc_tests(requested, label):
    groups = [
        pd.Series([1.0, 1.1, 1.2, 1.3]),
        pd.Series([2.0, 2.1, 2.2, 2.3]),
        pd.Series([4.0, 4.1, 4.2, 4.3]),
    ]
    comparisons = ["1-2", "1-3", "2-3"]

    results, _, _, results_dict, posthoc = runOWA(
        groups,
        comparisons,
        {},
        posthoc=requested,
    )

    assert posthoc == label
    assert results == results_dict[label.replace(" ", "-")][1]
    assert len(results) == len(comparisons)


def test_run_ttest_uses_brown_forsythe_to_choose_welch():
    low_variance = pd.Series([1.0, 1.1, 1.2, 1.1, 1.0, 1.2])
    high_variance = pd.Series([-5.0, -2.0, 1.0, 4.0, 7.0, 10.0])
    results_dict = {}

    _p, _ann, _overall, out, posthoc = runITTest(
        low_variance,
        high_variance,
        results_dict,
    )

    assert posthoc == "Welch's t-test"
    assert out["Equal variance"][0] is False
    assert "Welch's T Test" in out


def test_multiple_comparisons_can_force_welch_anova_games_howell():
    groups = [
        pd.Series([0.9, 1.0, 1.1, 1.0, 0.95, 1.05]),
        pd.Series([-4.0, -1.0, 2.0, 5.0, 8.0, 11.0]),
        pd.Series([2.9, 3.0, 3.1, 3.0, 2.95, 3.05]),
    ]
    exp = SimpleNamespace(
        condition_list=[_Condition("A"), _Condition("B"), _Condition("C")],
        data_path=".",
    )

    test, posthoc, _ann, results_dict = multipleComparisons(
        exp,
        groups,
        ax=None,
        fig=None,
        scatter=None,
        bar=None,
        draw=False,
        stats_test="welch_anova",
        posthoc="Games-Howell",
        comparisons=["1-2", "1-3", "2-3"],
        multiple_comparison="One-Way",
    )

    assert test == "Welch ANOVA"
    assert posthoc == "Games-Howell"
    assert "Welch ANOVA" in results_dict
    assert "Games-Howell" in results_dict


def test_multiple_comparisons_linear_model_with_covariate():
    rows = []
    for group, offset in (("A", 0.0), ("B", 1.0), ("C", 2.0)):
        for age in range(6):
            rows.append({
                "Group": group,
                "Y": offset + age * 0.25,
                "Age": age,
            })
    df = pd.DataFrame(rows)
    groups = [df.loc[df["Group"] == group, "Y"] for group in ["A", "B", "C"]]
    exp = SimpleNamespace(
        condition_list=[_Condition("A"), _Condition("B"), _Condition("C")],
        data_path=".",
    )

    test, posthoc, _ann, results_dict = multipleComparisons(
        exp,
        groups,
        ax=None,
        fig=None,
        scatter=None,
        bar=None,
        draw=False,
        stats_test="linear_model",
        model_df=df,
        model_group_col="Group",
        model_value_col="Y",
        covariates=["Age"],
        group_labels=["A", "B", "C"],
        comparisons=["1-2", "1-3", "2-3"],
    )

    assert test == "Linear Model"
    assert posthoc == "model contrasts HC3 Uncorrected"
    assert results_dict["Linear Model"][1] < 0.001
    assert "Linear-Model-Contrasts-Uncorrected" in results_dict


def test_adjacent_comparison_brackets_share_tier_until_a_line_is_covered():
    fig, ax = plt.subplots()
    try:
        bar = ax.bar([0, 1, 2], [1, 2, 3])
        ax.scatter([0, 1, 2], [1, 2, 3])

        plot_comparison_lines_from_figdata(
            ax,
            bar,
            ax,
            annotations=["****", "****", "****"],
            comparisons=["1-2", "2-3", "1-3"],
            group_values=[
                pd.Series([1.0, 1.1]),
                pd.Series([2.0, 2.1]),
                pd.Series([3.0, 3.1]),
            ],
            group_positions=[0, 1, 2],
            draw_error_bars=False,
        )

        star_ys = [text.get_position()[1] for text in ax.texts if text.get_text() == "****"]
        assert len(star_ys) == 3
        assert star_ys[1] == pytest.approx(star_ys[0])
        assert star_ys[2] > star_ys[0]
    finally:
        plt.close(fig)


def _comparison_geometry_in_display_units(
    y_limits,
    group_values,
    annotations=("ns", "ns", "*"),
):
    fig, ax = plt.subplots(figsize=(2, 5))
    ax.set_ylim(*y_limits)
    bar = ax.bar([0, 1, 2], [series.mean() for series in group_values])
    ax.scatter([0, 1, 2], [series.mean() for series in group_values])
    plot_comparison_lines_from_figdata(
        ax,
        bar,
        ax,
        annotations=list(annotations),
        comparisons=["1-2", "2-3", "1-3"],
        group_values=group_values,
        group_positions=[0, 1, 2],
        max_override=y_limits[1],
        draw_error_bars=False,
    )
    fig.canvas.draw()

    bracket_lines = ax.lines
    verticals = bracket_lines[0::3]
    horizontals = bracket_lines[2::3]

    def display_y(y):
        return float(ax.transData.transform((0.0, y))[1])

    handle_heights = [
        abs(display_y(line.get_ydata()[1]) - display_y(line.get_ydata()[0]))
        for line in verticals
    ]
    horizontal_ys = [display_y(line.get_ydata()[0]) for line in horizontals]
    text_ys = [display_y(text.get_position()[1]) for text in ax.texts]
    geometry = {
        "handle_heights": handle_heights,
        "tier_gap": horizontal_ys[2] - horizontal_ys[0],
        "text_offsets": [text_y - line_y for text_y, line_y in zip(text_ys, horizontal_ys)],
        "tight_height": float(fig.get_tightbbox(fig.canvas.get_renderer()).height),
    }
    plt.close(fig)
    return geometry


def test_comparison_geometry_is_fixed_across_positive_and_signed_y_ranges():
    positive = _comparison_geometry_in_display_units(
        (0.0, 20.0),
        [
            pd.Series([14.0, 15.0]),
            pd.Series([14.5, 15.5]),
            pd.Series([13.5, 14.5]),
        ],
    )
    signed = _comparison_geometry_in_display_units(
        (-2.0, 3.0),
        [
            pd.Series([-1.0, -0.5]),
            pd.Series([-0.2, 0.3]),
            pd.Series([0.2, 1.0]),
        ],
    )

    assert signed["handle_heights"] == pytest.approx(positive["handle_heights"])
    assert signed["tier_gap"] == pytest.approx(positive["tier_gap"])
    assert signed["text_offsets"] == pytest.approx(positive["text_offsets"])


def test_comparison_height_reserve_fixes_tight_canvas_across_annotation_glyphs():
    positive = _comparison_geometry_in_display_units(
        (0.0, 20.0),
        [
            pd.Series([14.0, 15.0]),
            pd.Series([14.5, 15.5]),
            pd.Series([13.5, 14.5]),
        ],
        annotations=("ns", "ns", "ns"),
    )
    signed = _comparison_geometry_in_display_units(
        (-2.0, 3.0),
        [
            pd.Series([-1.0, -0.5]),
            pd.Series([-0.2, 0.3]),
            pd.Series([0.2, 1.0]),
        ],
        annotations=("ns", "ns", "*"),
    )

    assert signed["tight_height"] == pytest.approx(positive["tight_height"])


def test_negative_mean_error_bar_points_away_from_zero():
    fig, ax = plt.subplots()
    try:
        bar = ax.bar([0, 1], [-1.0, 1.0])
        ax.scatter([0, 1], [-1.0, 1.0])
        negative = pd.Series([-1.4, -1.0, -0.6])
        positive = pd.Series([0.6, 1.0, 1.4])

        plot_comparison_lines_from_figdata(
            ax,
            bar,
            ax,
            annotations=[],
            comparisons=[],
            group_values=[negative, positive],
            group_positions=[0, 1],
        )

        vertical_error_lines = [
            line for line in ax.lines
            if len(line.get_xdata()) == 2
            and line.get_xdata()[0] == line.get_xdata()[1]
        ]
        negative_line = next(
            line for line in vertical_error_lines if line.get_xdata()[0] == 0
        )
        positive_line = next(
            line for line in vertical_error_lines if line.get_xdata()[0] == 1
        )
        assert min(negative_line.get_ydata()) < negative.mean()
        assert max(positive_line.get_ydata()) > positive.mean()
    finally:
        plt.close(fig)
