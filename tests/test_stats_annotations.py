import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from PyFLASH.stats import (
    STATS_ANNOTATION_X,
    STATS_ANNOTATION_Y,
    _annotate_stats_error,
    _annotate_stats_summary,
    runKW,
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
