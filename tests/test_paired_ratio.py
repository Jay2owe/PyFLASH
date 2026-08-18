import matplotlib

matplotlib.use("Agg")

import numpy as np
import pandas as pd
import pytest

from PyFLASH import ConditionBuilder, from_dataframe, report
from PyFLASH.aesthetics import pyflash_point_size
import PyFLASH.plotting as P


@pytest.fixture(autouse=True)
def _clean_report():
    report.collect()
    yield
    report.collect()


def _ratio_frame():
    rows = []
    for group, multiplier in (("Control", 1.10), ("MCI", 0.90), ("AD", 0.65)):
        for i in range(8):
            morning = 100.0 + i
            evening = morning * multiplier * (1.0 + (i - 3.5) * 0.01)
            rows.append({
                "Subject": f"{group}{i}",
                "Diagnosis": group,
                "Time": "WeekEight",
                "Morning": morning,
                "Evening": evening,
            })
    return pd.DataFrame(rows)


def _exp(tmp_path):
    conditions = (
        ConditionBuilder("Diagnosis")
        .add("Control", color="grey")
        .add("MCI", color="#5757F9")
        .add("AD", color="red")
        .build()
    )
    return from_dataframe(
        _ratio_frame(),
        conditions=conditions,
        condition_col="Diagnosis",
        animal_col="Subject",
        fig_path=tmp_path / "figures",
        data_path=tmp_path / "data",
    )


def test_paired_ratio_log_mode_uses_second_over_first_and_reports(tmp_path):
    exp = _exp(tmp_path)

    report.start()
    out = P.plot_paired_ratio(
        exp,
        data_cols=["Morning", "Evening"],
        factor="Diagnosis",
        log_transform=True,
        save=False,
        return_data=True,
    )
    records = report.collect()

    means = dict(zip(out["summary"]["group"], out["summary"]["mean"]))
    assert means["Control"] == pytest.approx(1.1, rel=0.03)
    assert means["MCI"] == pytest.approx(0.9, rel=0.03)
    assert means["AD"] == pytest.approx(0.65, rel=0.03)
    assert out["overall"]["test"] == "One-way ANOVA on log ratios"
    assert set(out["pairwise"]["effect_label"]) == {"ratio_of_ratios"}
    assert "AD vs Control" in set(out["pairwise"]["direction"])
    assert out["figure"].axes[0].get_yscale() == "log"
    assert out["peak_summary"]["endpoint"].tolist() == [
        "denominator", "numerator",
        "denominator", "numerator",
        "denominator", "numerator",
    ]
    assert records and records[0]["kind"] == "group_comparison"
    assert records[0]["raw_stats"]["scale"] == "log_ratio"


def test_paired_ratio_raw_mode_changes_test_scale(tmp_path):
    out = P.plot_paired_ratio(
        _exp(tmp_path),
        data_cols=["Morning", "Evening"],
        factor="Diagnosis",
        log_transform=False,
        primary_comparison="AD vs Control",
        save=False,
        return_data=True,
    )

    assert out["overall"]["test"] == "One-way ANOVA on raw ratios"
    assert set(out["pairwise"]["effect_label"]) == {"difference"}
    assert out["figure"].axes[0].get_yscale() == "linear"
    assert any(
        "Primary AD vs Control: difference=" in text.get_text()
        for text in out["figure"].axes[0].texts
    )


def test_paired_ratio_column_labels_remap_ratio_axis(tmp_path):
    fig = P.plot_paired_ratio(
        _exp(tmp_path),
        data_cols=["Morning", "Evening"],
        factor="Diagnosis",
        column_labels=["AM peak", "PM peak"],
        save=False,
    )

    assert [tick.get_text() for tick in fig.axes[0].get_xticklabels()] == ["AM peak", "PM peak"]


def test_paired_ratio_uses_standard_stats_summary_and_clean_mean_markers(tmp_path):
    out = P.plot_paired_ratio(
        _exp(tmp_path),
        data_cols=["Morning", "Evening"],
        factor="Diagnosis",
        title="Paired endpoint example",
        footer="auto",
        save=False,
        return_data=True,
    )
    fig = out["figure"]
    ax = fig.axes[0]

    assert not fig.patches
    stats_text = next(
        text for text in ax.texts
        if "Test: One-way ANOVA on log ratios" in text.get_text()
    )
    assert stats_text.get_position()[1] == pytest.approx(0.88)
    comparison_texts = [
        text.get_text() for text in ax.texts
        if " change " in text.get_text()
    ]
    assert comparison_texts
    assert any("AD vs Control change" in text for text in comparison_texts)
    assert not any(text.endswith(" ns") for text in comparison_texts)
    assert all(
        text.get_color() == "#111111"
        for text in ax.texts
        if " change " in text.get_text()
    )
    comparison_lines = [line for line in ax.lines if line.get_zorder() == 8]
    assert comparison_lines
    assert all(line.get_color() == "#111111" for line in comparison_lines)
    assert ax.get_position().y0 >= 0.24
    legend = ax.get_legend()
    assert legend is not None
    assert legend._loc == 3  # lower-left anchor keeps the legend above the axis.
    assert legend.get_bbox_to_anchor()._bbox.y0 > 1.0
    legend_labels = [text.get_text() for text in legend.get_texts()]
    assert legend_labels == ["Control", "MCI", "AD"]
    assert not any("n=" in label for label in legend_labels)

    summary_lines = [line for line in ax.lines if line.get_linewidth() == pytest.approx(3.0)]
    assert summary_lines
    assert {line.get_zorder() for line in summary_lines} == {5}

    errorbar_collections = [
        collection for collection in ax.collections
        if type(collection).__name__ == "LineCollection"
    ]
    assert errorbar_collections
    assert {collection.get_zorder() for collection in errorbar_collections} == {5}

    mean_dot_collections = [
        collection for collection in ax.collections
        if type(collection).__name__ == "PathCollection" and collection.get_zorder() == 5
    ]
    assert mean_dot_collections
    assert all(collection.get_edgecolors().size > 0 for collection in mean_dot_collections)
    assert all(
        np.allclose(collection.get_edgecolors(), collection.get_facecolors())
        for collection in mean_dot_collections
    )

    sample_dot_collections = [
        collection for collection in ax.collections
        if type(collection).__name__ == "PathCollection" and collection.get_zorder() == 3
    ]
    assert sample_dot_collections
    default_sample_diameter = pyflash_point_size(None, backend="points") * 0.5
    expected_default_size = pyflash_point_size(default_sample_diameter, backend="area")
    assert all(
        collection.get_sizes()[0] == pytest.approx(expected_default_size)
        for collection in sample_dot_collections
    )
    assert all(
        mean_collection.get_sizes()[0] > sample_dot_collections[0].get_sizes()[0]
        for mean_collection in mean_dot_collections
    )


def test_paired_ratio_sample_line_and_dot_controls(tmp_path):
    out = P.plot_paired_ratio(
        _exp(tmp_path),
        data_cols=["Morning", "Evening"],
        factor="Diagnosis",
        sample_dot_size=17,
        sample_line_width=2.75,
        save=False,
        return_data=True,
    )
    ax = out["figure"].axes[0]

    sample_lines = [line for line in ax.lines if line.get_zorder() == 1]
    assert sample_lines
    assert all(line.get_linewidth() == pytest.approx(2.75) for line in sample_lines)

    sample_dots = [
        collection for collection in ax.collections
        if type(collection).__name__ == "PathCollection" and collection.get_zorder() == 3
    ]
    assert sample_dots
    expected_size = pyflash_point_size(17, backend="area")
    assert all(collection.get_sizes()[0] == pytest.approx(expected_size) for collection in sample_dots)

    point_alias = P.plot_paired_ratio(
        _exp(tmp_path),
        data_cols=["Morning", "Evening"],
        factor="Diagnosis",
        point_size=13,
        save=False,
        return_data=True,
    )
    alias_dots = [
        collection for collection in point_alias["figure"].axes[0].collections
        if type(collection).__name__ == "PathCollection" and collection.get_zorder() == 3
    ]
    assert alias_dots
    expected_alias_size = pyflash_point_size(13, backend="area")
    assert all(collection.get_sizes()[0] == pytest.approx(expected_alias_size) for collection in alias_dots)

    mean_override = P.plot_paired_ratio(
        _exp(tmp_path),
        data_cols=["Morning", "Evening"],
        factor="Diagnosis",
        mean_marker_size=15,
        save=False,
        return_data=True,
    )
    mean_override_dots = [
        collection for collection in mean_override["figure"].axes[0].collections
        if type(collection).__name__ == "PathCollection" and collection.get_zorder() == 5
    ]
    assert mean_override_dots
    expected_mean_size = pyflash_point_size(15, backend="area")
    assert all(
        collection.get_sizes()[0] == pytest.approx(expected_mean_size)
        for collection in mean_override_dots
    )

    no_lines = P.plot_paired_ratio(
        _exp(tmp_path),
        data_cols=["Morning", "Evening"],
        factor="Diagnosis",
        show_sample_lines=False,
        save=False,
        return_data=True,
    )
    assert not [line for line in no_lines["figure"].axes[0].lines if line.get_zorder() == 1]

    no_comparisons = P.plot_paired_ratio(
        _exp(tmp_path),
        data_cols=["Morning", "Evening"],
        factor="Diagnosis",
        show_comparisons=False,
        save=False,
        return_data=True,
    )
    assert not [
        text for text in no_comparisons["figure"].axes[0].texts
        if " change " in text.get_text()
    ]

    no_legend = P.plot_paired_ratio(
        _exp(tmp_path),
        data_cols=["Morning", "Evening"],
        factor="Diagnosis",
        show_legend=False,
        save=False,
        return_data=True,
    )
    assert no_legend["figure"].axes[0].get_legend() is None


def test_paired_ratio_can_use_nonparametric_dunn_posthoc(tmp_path):
    out = P.plot_paired_ratio(
        _exp(tmp_path),
        data_cols=["Morning", "Evening"],
        factor="Diagnosis",
        ratio_test="kruskal",
        posthoc="Dunn",
        pairwise_correction="Holm",
        save=False,
        return_data=True,
    )

    assert out["overall"]["test"] == "Kruskal-Wallis on log ratios"
    assert set(out["pairwise"]["posthoc"]) == {"Dunn Holm"}
    assert set(out["pairwise"]["p_correction"]) == {"Holm"}


def test_paired_ratio_can_use_tukey_and_permutation_options(tmp_path):
    tukey = P.plot_paired_ratio(
        _exp(tmp_path),
        data_cols=["Morning", "Evening"],
        factor="Diagnosis",
        ratio_test="anova",
        posthoc="Tukey",
        save=False,
        return_data=True,
    )
    assert tukey["overall"]["test"] == "One-way ANOVA on log ratios"
    assert set(tukey["pairwise"]["posthoc"]) == {"Tukey"}
    assert set(tukey["pairwise"]["p_correction"]) == {"tukey"}

    perm = P.plot_paired_ratio(
        _exp(tmp_path),
        data_cols=["Morning", "Evening"],
        factor="Diagnosis",
        ratio_test="permutation",
        posthoc="permutation",
        n_permutations=99,
        random_state=1,
        save=False,
        return_data=True,
    )
    assert perm["overall"]["test"] == "Permutation omnibus on log ratios"
    assert set(perm["pairwise"]["posthoc"]) == {"Permutation"}


def test_paired_ratio_accepts_raw_dataframe_input(tmp_path):
    out = P.plot_paired_ratio(
        _ratio_frame(),
        data_cols=["Morning", "Evening"],
        factor="Diagnosis",
        condition_col="Diagnosis",
        animal_col="Subject",
        dataframe_kwargs={
            "fig_path": tmp_path / "figures",
            "data_path": tmp_path / "data",
        },
        save=False,
        return_data=True,
    )

    assert out["summary"]["group"].tolist() == ["Control", "MCI", "AD"]
    assert out["summary"]["n"].tolist() == [8, 8, 8]


def test_paired_ratio_specificity_queue_returns_children(tmp_path):
    df = pd.concat([
        _ratio_frame().assign(Time="WeekFour"),
        _ratio_frame().assign(Time="WeekEight"),
    ], ignore_index=True)
    conditions = (
        ConditionBuilder("Diagnosis")
        .add("Control")
        .add("MCI")
        .add("AD")
        .build()
    )
    exp = from_dataframe(
        df,
        conditions=conditions,
        condition_col="Diagnosis",
        animal_col="Subject",
        fig_path=tmp_path / "figures",
        data_path=tmp_path / "data",
    )

    out = P.plot_paired_ratio(
        exp,
        data_cols=["Morning", "Evening"],
        factor="Diagnosis",
        specificity=[("Time", "WeekFour"), ("Time", "WeekEight")],
        save=False,
        return_data=True,
    )

    assert set(out) == {("Time", "WeekFour"), ("Time", "WeekEight")}
    assert all(child["summary"]["n"].tolist() == [8, 8, 8] for child in out.values())
