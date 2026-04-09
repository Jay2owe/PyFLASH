import matplotlib
import pandas as pd

from matplotlib.axes import Axes
from types import SimpleNamespace

from IF_analysis.conditions import condition, conditionList

matplotlib.use("Agg")

from IF_analysis import plotting


def _build_marker_specificity_experiment():
    summary = pd.DataFrame(
        [
            {"AnimalName": "A1", "Condition": "Syn", "Genotype": "Syn", "Time": "WeekFour"},
            {"AnimalName": "A2", "Condition": "Syn", "Genotype": "Syn", "Time": "WeekEight"},
            {"AnimalName": "B1", "Condition": "APP", "Genotype": "APP", "Time": "WeekFour"},
            {"AnimalName": "B2", "Condition": "APP", "Genotype": "APP", "Time": "WeekEight"},
        ]
    )
    marker_df = pd.DataFrame(
        [
            {
                "AnimalName": "A1",
                "Condition": "Syn",
                "Genotype": "Syn",
                "Time": "WeekFour",
                "CK1d_Coloc_mCherry": 10,
                "CK1d_MetricA": 1,
                "CK1d_MetricB": 1,
            },
            {
                "AnimalName": "A1",
                "Condition": "Syn",
                "Genotype": "Syn",
                "Time": "WeekFour",
                "CK1d_Coloc_mCherry": 40,
                "CK1d_MetricA": 2,
                "CK1d_MetricB": 4,
            },
            {
                "AnimalName": "A2",
                "Condition": "Syn",
                "Genotype": "Syn",
                "Time": "WeekEight",
                "CK1d_Coloc_mCherry": 5,
                "CK1d_MetricA": 1,
                "CK1d_MetricB": 3,
            },
            {
                "AnimalName": "A2",
                "Condition": "Syn",
                "Genotype": "Syn",
                "Time": "WeekEight",
                "CK1d_Coloc_mCherry": 15,
                "CK1d_MetricA": 2,
                "CK1d_MetricB": 2,
            },
            {
                "AnimalName": "A2",
                "Condition": "Syn",
                "Genotype": "Syn",
                "Time": "WeekEight",
                "CK1d_Coloc_mCherry": 25,
                "CK1d_MetricA": 3,
                "CK1d_MetricB": 1,
            },
            {
                "AnimalName": "B1",
                "Condition": "APP",
                "Genotype": "APP",
                "Time": "WeekFour",
                "CK1d_Coloc_mCherry": 35,
                "CK1d_MetricA": 1,
                "CK1d_MetricB": 1,
            },
            {
                "AnimalName": "B1",
                "Condition": "APP",
                "Genotype": "APP",
                "Time": "WeekFour",
                "CK1d_Coloc_mCherry": 45,
                "CK1d_MetricA": 2,
                "CK1d_MetricB": 4,
            },
            {
                "AnimalName": "B1",
                "Condition": "APP",
                "Genotype": "APP",
                "Time": "WeekFour",
                "CK1d_Coloc_mCherry": 55,
                "CK1d_MetricA": 3,
                "CK1d_MetricB": 9,
            },
            {
                "AnimalName": "B2",
                "Condition": "APP",
                "Genotype": "APP",
                "Time": "WeekEight",
                "CK1d_Coloc_mCherry": 20,
                "CK1d_MetricA": 1,
                "CK1d_MetricB": 16,
            },
            {
                "AnimalName": "B2",
                "Condition": "APP",
                "Genotype": "APP",
                "Time": "WeekEight",
                "CK1d_Coloc_mCherry": 60,
                "CK1d_MetricA": 2,
                "CK1d_MetricB": 9,
            },
            {
                "AnimalName": "B2",
                "Condition": "APP",
                "Genotype": "APP",
                "Time": "WeekEight",
                "CK1d_Coloc_mCherry": 70,
                "CK1d_MetricA": 3,
                "CK1d_MetricB": 4,
            },
            {
                "AnimalName": "B2",
                "Condition": "APP",
                "Genotype": "APP",
                "Time": "WeekEight",
                "CK1d_Coloc_mCherry": 80,
                "CK1d_MetricA": 4,
                "CK1d_MetricB": 1,
            },
        ]
    )
    comboany_labels = [
        "None",
        "GFAP+",
        "None",
        "mCherry+",
        "GFAP+_mCherry+",
        "GFAP+",
        "mCherry+",
        "GFAP+_mCherry+",
        "None",
        "None",
        "mCherry+",
        "GFAP+_mCherry+",
    ]
    combo_labels = [
        "None",
        "GFAP+",
        "None",
        "wmCherry",
        "GFAP+_wmCherry",
        "GFAP+",
        "wmCherry",
        "GFAP+_wmCherry",
        "None",
        "None",
        "wmCherry",
        "GFAP+_wmCherry",
    ]
    comboany_signatures = ["None", "GFAP+", "mCherry+", "GFAP+_mCherry+"]
    combo_signatures = ["None", "GFAP+", "wmCherry", "GFAP+_wmCherry"]
    for signature in comboany_signatures:
        values = [1 if label == signature else 0 for label in comboany_labels]
        marker_df[f"CK1d_VolComboAny_{signature}"] = values
        marker_df[f"CK1d_CPCComboAny_{signature}"] = values
    for signature in combo_signatures:
        values = [1 if label == signature else 0 for label in combo_labels]
        marker_df[f"CK1d_VolCombo_{signature}"] = values
        marker_df[f"CK1d_CPCCombo_{signature}"] = values

    conds = conditionList(
        [
            condition("Syn", "Syn", "#111111", "Genotype"),
            condition("APP", "APP", "#222222", "Genotype"),
        ]
    )

    return SimpleNamespace(
        summary=summary.copy(),
        summaries={"SCN": summary.copy()},
        data={"CK1d": SimpleNamespace(df=marker_df)},
        condition_list=conds,
        factorDict=conds.factorDict,
        fig_path=".",
    )


def _specificity_queue():
    return [("Time", "WeekFour"), ("Time", "WeekEight")]


def test_plot_mean_bars_runs_without_nameerror_in_teardown(tmp_path, monkeypatch):
    experiment = _build_marker_specificity_experiment()
    experiment.summary["CK1d_Count"] = [1.0, 2.0, 3.0, 4.0]
    experiment.summaries["SCN"] = experiment.summary.copy()
    experiment.fig_path = str(tmp_path)
    experiment.data_path = str(tmp_path)

    monkeypatch.setattr(plotting, "save_fig", lambda *args, **kwargs: None)

    plotting.plot_mean_bars(
        experiment,
        filtered_columns=["CK1d_Count"],
        points=False,
        save=False,
    )


def test_plot_pie_charts_specificity_queue_filters_each_pie_independently():
    experiment = _build_marker_specificity_experiment()

    result = plotting.plot_pie_charts(
        experiment,
        marker="CK1d",
        x_attr="Coloc_mCherry",
        threshold=[30],
        show_counts=True,
        show_pct=False,
        plot_format="pie",
        factor="Genotype",
        specificity=_specificity_queue(),
        save=False,
    )

    week_four = result[("Time", "WeekFour")]
    week_eight = result[("Time", "WeekEight")]

    assert week_four["group"] == ["Syn", "APP"]
    assert week_eight["group"] == ["Syn", "APP"]

    assert week_four["pie_counts"] == [[1, 1], [3]]
    assert week_four["pie_labels"] == [["<= 30", "> 30"], ["> 30"]]

    assert week_eight["pie_counts"] == [[3], [1, 3]]
    assert week_eight["pie_labels"] == [["<= 30"], ["<= 30", "> 30"]]


def test_plot_combo_pies_comboany_specificity_queue_counts_none_and_any_combinations():
    experiment = _build_marker_specificity_experiment()

    result = plotting.plot_combo_pies(
        experiment,
        marker="CK1d",
        family="VolComboAny",
        show_counts=True,
        show_pct=False,
        plot_format="pie",
        factor="Genotype",
        specificity=_specificity_queue(),
        save=False,
    )

    week_four = result[("Time", "WeekFour")]
    week_eight = result[("Time", "WeekEight")]

    assert week_four["group"] == ["Syn", "APP"]
    assert week_eight["group"] == ["Syn", "APP"]

    assert week_four["pie_labels"] == [
        ["None", "GFAP+"],
        ["GFAP+", "mCherry+", "GFAP+_mCherry+"],
    ]
    assert week_four["pie_counts"] == [[1, 1], [1, 1, 1]]

    assert week_eight["pie_labels"] == [
        ["None", "mCherry+", "GFAP+_mCherry+"],
        ["None", "mCherry+", "GFAP+_mCherry+"],
    ]
    assert week_eight["pie_counts"] == [[1, 1, 1], [2, 1, 1]]


def test_plot_combo_pies_combo_specificity_queue_counts_none_and_detailed_combinations():
    experiment = _build_marker_specificity_experiment()

    result = plotting.plot_combo_pies(
        experiment,
        marker="CK1d",
        family="VolCombo",
        show_counts=True,
        show_pct=False,
        plot_format="pie",
        factor="Genotype",
        specificity=_specificity_queue(),
        save=False,
    )

    week_four = result[("Time", "WeekFour")]
    week_eight = result[("Time", "WeekEight")]

    assert week_four["group"] == ["Syn", "APP"]
    assert week_eight["group"] == ["Syn", "APP"]

    assert week_four["pie_labels"] == [
        ["None", "GFAP+"],
        ["GFAP+", "wmCherry", "GFAP+_wmCherry"],
    ]
    assert week_four["pie_counts"] == [[1, 1], [1, 1, 1]]

    assert week_eight["pie_labels"] == [
        ["None", "wmCherry", "GFAP+_wmCherry"],
        ["None", "wmCherry", "GFAP+_wmCherry"],
    ]
    assert week_eight["pie_counts"] == [[1, 1, 1], [2, 1, 1]]


def test_plot_combo_pies_cpc_comboany_specificity_queue_counts_none_and_any_combinations():
    experiment = _build_marker_specificity_experiment()

    result = plotting.plot_combo_pies(
        experiment,
        marker="CK1d",
        family="CPCComboAny",
        show_counts=True,
        show_pct=False,
        plot_format="pie",
        factor="Genotype",
        specificity=_specificity_queue(),
        save=False,
    )

    week_four = result[("Time", "WeekFour")]
    week_eight = result[("Time", "WeekEight")]

    assert week_four["pie_labels"] == [
        ["None", "GFAP+"],
        ["GFAP+", "mCherry+", "GFAP+_mCherry+"],
    ]
    assert week_four["pie_counts"] == [[1, 1], [1, 1, 1]]

    assert week_eight["pie_labels"] == [
        ["None", "mCherry+", "GFAP+_mCherry+"],
        ["None", "mCherry+", "GFAP+_mCherry+"],
    ]
    assert week_eight["pie_counts"] == [[1, 1, 1], [2, 1, 1]]


def test_plot_pie_charts_include_n_adds_group_animal_counts_to_bar_labels(monkeypatch):
    experiment = _build_marker_specificity_experiment()
    labels_seen = []
    original = Axes.set_xticklabels

    def _recording_set_xticklabels(self, labels, *args, **kwargs):
        labels_seen.append([str(label) for label in labels])
        return original(self, labels, *args, **kwargs)

    monkeypatch.setattr(Axes, "set_xticklabels", _recording_set_xticklabels)

    result = plotting.plot_pie_charts(
        experiment,
        marker="CK1d",
        x_attr="Coloc_mCherry",
        threshold=[30],
        show_counts=True,
        show_pct=False,
        plot_format="bar",
        factor="Genotype",
        include_N=True,
        save=False,
    )

    assert result["n_animals"] == [2, 2]
    assert ["Syn\nN=2", "APP\nN=2"] in labels_seen


def test_plot_combo_pies_include_n_adds_animal_counts_to_titles(monkeypatch):
    experiment = _build_marker_specificity_experiment()
    titles_seen = []
    original = Axes.set_title

    def _recording_set_title(self, label, *args, **kwargs):
        titles_seen.append(str(label))
        return original(self, label, *args, **kwargs)

    monkeypatch.setattr(Axes, "set_title", _recording_set_title)

    result = plotting.plot_combo_pies(
        experiment,
        marker="CK1d",
        family="VolComboAny",
        show_counts=True,
        show_pct=False,
        plot_format="pie",
        factor="Genotype",
        include_N=True,
        save=False,
    )

    assert result["n_animals"] == [2, 2]
    assert len(titles_seen) == 2
    assert all(title.endswith("(N=2)") for title in titles_seen)


def test_plot_pie_charts_show_counts_and_pct_adds_dual_bar_labels(monkeypatch):
    experiment = _build_marker_specificity_experiment()
    text_seen = []
    original = Axes.text

    def _recording_text(self, x, y, s, *args, **kwargs):
        text_seen.append(str(s))
        return original(self, x, y, s, *args, **kwargs)

    monkeypatch.setattr(Axes, "text", _recording_text)

    plotting.plot_pie_charts(
        experiment,
        marker="CK1d",
        x_attr="Coloc_mCherry",
        threshold=[30],
        plot_format="bar",
        factor="Genotype",
        show_counts=True,
        show_pct=True,
        save=False,
    )

    assert any(
        label.count("\n") == 1
        and label.split("\n")[0].isdigit()
        and label.endswith("%")
        for label in text_seen
    )


def test_plot_combo_pies_show_counts_and_pct_builds_dual_pie_labels(monkeypatch):
    experiment = _build_marker_specificity_experiment()
    autopct_seen = []

    def _recording_pie(self, x, *args, autopct=None, **kwargs):
        values = [float(v) for v in x]
        total = sum(values)
        if callable(autopct) and total > 0:
            first_pct = 100.0 * values[0] / total
            autopct_seen.append(autopct(first_pct))
        return [], [], []

    monkeypatch.setattr(Axes, "pie", _recording_pie)

    plotting.plot_combo_pies(
        experiment,
        marker="CK1d",
        family="VolComboAny",
        plot_format="pie",
        factor="Genotype",
        specificity=("Time", "WeekFour"),
        show_counts=True,
        show_pct=True,
        save=False,
    )

    assert any("\n" in label and "%" in label for label in autopct_seen)


def test_plot_pie_charts_order_reorders_bins_clockwise_from_top(monkeypatch):
    experiment = _build_marker_specificity_experiment()
    pies_seen = []

    def _recording_pie(self, x, *args, labels=None, startangle=None, counterclock=None, **kwargs):
        pies_seen.append(
            {
                "counts": [int(v) for v in x],
                "labels": [str(label) for label in labels],
                "startangle": float(startangle),
                "counterclock": bool(counterclock),
            }
        )
        return [], [], []

    monkeypatch.setattr(Axes, "pie", _recording_pie)

    result = plotting.plot_pie_charts(
        experiment,
        marker="CK1d",
        x_attr="Coloc_mCherry",
        threshold=[30],
        factor="Genotype",
        specificity=("Time", "WeekFour"),
        show_counts=True,
        show_pct=False,
        order=["> 30", "<= 30"],
        save=False,
    )

    assert result["pie_raw_labels"] == [["> 30", "<= 30"], ["> 30"]]
    assert result["pie_labels"] == [["> 30", "<= 30"], ["> 30"]]
    assert pies_seen[0]["labels"] == ["> 30", "<= 30"]
    assert pies_seen[0]["counts"] == [1, 1]
    assert all(call["startangle"] == 90.0 for call in pies_seen)
    assert all(call["counterclock"] is False for call in pies_seen)


def test_plot_pie_charts_labels_remap_displayed_bins():
    experiment = _build_marker_specificity_experiment()

    result = plotting.plot_pie_charts(
        experiment,
        marker="CK1d",
        x_attr="Coloc_mCherry",
        threshold=[30],
        factor="Genotype",
        specificity=("Time", "WeekFour"),
        show_counts=True,
        show_pct=False,
        labels={"<= 30": "Negative", "> 30": "Positive"},
        save=False,
    )

    assert result["pie_raw_labels"] == [["<= 30", "> 30"], ["> 30"]]
    assert result["pie_labels"] == [["Negative", "Positive"], ["Positive"]]


def test_plot_pie_charts_titles_include_group_and_specificity_context(monkeypatch):
    experiment = _build_marker_specificity_experiment()
    titles_seen = []
    original = Axes.set_title

    def _recording_set_title(self, label, *args, **kwargs):
        titles_seen.append(str(label))
        return original(self, label, *args, **kwargs)

    monkeypatch.setattr(Axes, "set_title", _recording_set_title)

    plotting.plot_pie_charts(
        experiment,
        marker="CK1d",
        x_attr="Coloc_mCherry",
        threshold=[30],
        factor="Genotype",
        specificity=("Time", "WeekFour"),
        show_counts=True,
        show_pct=False,
        save=False,
    )

    assert len(titles_seen) == 2
    assert any("Syn" in title and "WeekFour" in title for title in titles_seen)
    assert any("APP" in title and "WeekFour" in title for title in titles_seen)


def test_plot_pie_charts_bar_order_uses_raw_category_order_after_label_remap(monkeypatch):
    experiment = _build_marker_specificity_experiment()
    legend_labels_seen = []
    original = Axes.legend

    def _recording_legend(self, handles, labels, *args, **kwargs):
        legend_labels_seen.append([str(label) for label in labels])
        return original(self, handles, labels, *args, **kwargs)

    monkeypatch.setattr(Axes, "legend", _recording_legend)

    plotting.plot_pie_charts(
        experiment,
        marker="CK1d",
        x_attr="Coloc_mCherry",
        threshold=[30],
        factor="Genotype",
        plot_format="bar",
        show_counts=True,
        show_pct=False,
        labels={"<= 30": "Negative", "> 30": "Positive"},
        order=["> 30", "<= 30"],
        save=False,
    )

    assert ["Positive", "Negative"] in legend_labels_seen


def test_plot_combo_pies_can_collapse_comboany_marker_at_plot_time():
    experiment = _build_marker_specificity_experiment()

    result = plotting.plot_combo_pies(
        experiment,
        marker="CK1d",
        family="VolComboAny",
        show_counts=True,
        show_pct=False,
        plot_format="pie",
        factor="Genotype",
        specificity=_specificity_queue(),
        collapse_markers="GFAP",
        save=False,
    )

    week_four = result[("Time", "WeekFour")]
    week_eight = result[("Time", "WeekEight")]

    assert week_four["pie_labels"] == [
        ["None"],
        ["None", "mCherry+"],
    ]
    assert week_four["pie_counts"] == [[2], [1, 2]]

    assert week_eight["pie_labels"] == [
        ["None", "mCherry+"],
        ["None", "mCherry+"],
    ]
    assert week_eight["pie_counts"] == [[1, 2], [2, 2]]


def test_plot_combo_pies_order_reorders_combo_signatures():
    experiment = _build_marker_specificity_experiment()

    result = plotting.plot_combo_pies(
        experiment,
        marker="CK1d",
        family="VolComboAny",
        show_counts=True,
        show_pct=False,
        plot_format="pie",
        factor="Genotype",
        specificity=("Time", "WeekFour"),
        order=["GFAP+_mCherry+", "mCherry+", "GFAP+", "None"],
        save=False,
    )

    assert result["pie_labels"] == [
        ["GFAP+", "None"],
        ["GFAP+_mCherry+", "mCherry+", "GFAP+"],
    ]
    assert result["pie_counts"] == [[1, 1], [1, 1, 1]]


def test_plot_combo_pies_can_collapse_detailed_combo_marker_at_plot_time():
    experiment = _build_marker_specificity_experiment()

    result = plotting.plot_combo_pies(
        experiment,
        marker="CK1d",
        family="VolCombo",
        show_counts=True,
        show_pct=False,
        plot_format="pie",
        factor="Genotype",
        specificity=_specificity_queue(),
        collapse_markers="GFAP",
        save=False,
    )

    week_four = result[("Time", "WeekFour")]
    week_eight = result[("Time", "WeekEight")]

    assert week_four["pie_labels"] == [
        ["None"],
        ["None", "wmCherry"],
    ]
    assert week_four["pie_counts"] == [[2], [1, 2]]

    assert week_eight["pie_labels"] == [
        ["None", "wmCherry"],
        ["None", "wmCherry"],
    ]
    assert week_eight["pie_counts"] == [[1, 2], [2, 2]]


def test_plot_combo_pies_labels_remap_collapsed_signatures():
    experiment = _build_marker_specificity_experiment()

    result = plotting.plot_combo_pies(
        experiment,
        marker="CK1d",
        family="VolComboAny",
        show_counts=True,
        show_pct=False,
        plot_format="pie",
        factor="Genotype",
        specificity=("Time", "WeekFour"),
        collapse_markers="GFAP",
        labels={
            "None": "Non-mCherry and Non-Nuclear",
            "mCherry+": "mCherry Cytoplasm",
        },
        save=False,
    )

    assert result["pie_raw_labels"] == [["None"], ["None", "mCherry+"]]
    assert result["pie_labels"] == [
        ["Non-mCherry and Non-Nuclear"],
        ["Non-mCherry and Non-Nuclear", "mCherry Cytoplasm"],
    ]


def test_plot_ecdf_specificity_queue_filters_each_group_independently():
    experiment = _build_marker_specificity_experiment()

    result = plotting.plot_ecdf(
        experiment,
        marker="CK1d",
        x_attr="Coloc_mCherry",
        factor="Genotype",
        specificity=_specificity_queue(),
        save=False,
    )

    assert result[("Time", "WeekFour")]["group"] == ["Syn", "APP"]
    assert result[("Time", "WeekFour")]["n"] == [2, 3]
    assert result[("Time", "WeekEight")]["group"] == ["Syn", "APP"]
    assert result[("Time", "WeekEight")]["n"] == [3, 4]


def test_plot_ridgeline_specificity_queue_filters_each_group_independently():
    experiment = _build_marker_specificity_experiment()

    result = plotting.plot_ridgeline(
        experiment,
        marker="CK1d",
        x_attr="Coloc_mCherry",
        factor="Genotype",
        specificity=_specificity_queue(),
        save=False,
    )

    assert result[("Time", "WeekFour")]["group"] == ["Syn", "APP"]
    assert result[("Time", "WeekFour")]["n"] == [2, 3]
    assert result[("Time", "WeekEight")]["group"] == ["Syn", "APP"]
    assert result[("Time", "WeekEight")]["n"] == [3, 4]


def test_plot_histograms_specificity_queue_passes_active_filter(monkeypatch):
    experiment = _build_marker_specificity_experiment()

    def _recording_histogram_action(ctx, state, marker=None, x=None, **kwargs):
        df = ctx.experiment.data[marker].df.reset_index()
        df = plotting._filter_marker_df_for_context(ctx, df)
        specificity = kwargs.get("specificity_filter", kwargs.get("specificity"))
        df = plotting._filter_df_by_specificity(df, specificity)
        return {
            "group": ctx.factor_value or ctx.condition,
            "n": int(len(df)),
            "specificity_seen": tuple(specificity) if specificity is not None else None,
        }

    monkeypatch.setattr(plotting, "histogram_action", _recording_histogram_action)

    result = plotting.plot_histograms(
        experiment,
        marker="CK1d",
        x_attr="Coloc_mCherry",
        factor="Genotype",
        specificity=_specificity_queue(),
        save=False,
    )

    week_four = result[("Time", "WeekFour")]
    week_eight = result[("Time", "WeekEight")]

    assert week_four["group"] == ["Syn", "APP"]
    assert week_four["n"] == [2, 3]
    assert week_four["specificity_seen"] == [("Time", "WeekFour"), ("Time", "WeekFour")]

    assert week_eight["group"] == ["Syn", "APP"]
    assert week_eight["n"] == [3, 4]
    assert week_eight["specificity_seen"] == [("Time", "WeekEight"), ("Time", "WeekEight")]


def test_plot_matrices_marker_specificity_queue_filters_each_panel_independently():
    experiment = _build_marker_specificity_experiment()

    result = plotting.plot_matrices(
        experiment,
        filtered_columns=["CK1d_MetricA", "CK1d_MetricB"],
        marker="CK1d",
        factor="Genotype",
        specificity=_specificity_queue(),
        save=False,
        share_columns_across_panels=False,
    )

    pair_name = "CK1d_MetricA vs CK1d_MetricB"
    week_four_corrs = result[("Time", "WeekFour")]["correlations"]
    week_eight_corrs = result[("Time", "WeekEight")]["correlations"]

    assert week_four_corrs[0][pair_name][1] > 0.9
    assert week_four_corrs[1][pair_name][1] > 0.9
    assert week_eight_corrs[0][pair_name][1] < -0.9
    assert week_eight_corrs[1][pair_name][1] < -0.9
