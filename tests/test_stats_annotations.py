import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
import pytest
from statsmodels.stats.multitest import multipletests

from PyFLASH.stats import (
    STATS_ANNOTATION_X,
    STATS_ANNOTATION_Y,
    _annotate_stats_error,
    _annotate_stats_summary,
    plot_comparison_lines_from_figdata,
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


def test_adjacent_comparison_brackets_use_separate_tiers():
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
        assert star_ys[1] > star_ys[0]
    finally:
        plt.close(fig)
