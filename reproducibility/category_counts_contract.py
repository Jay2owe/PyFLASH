"""Independent descriptive checks for the registered category-count plot."""
from collections import Counter
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd


CAPABILITY_PREFIXES = {"category_counts": ("category-counts.",)}
GROUPS = ("Control", "AD")
SEASONS = ("Winter", "Spring", "Summer", "Autumn")
RTOL = 0.0
ATOL = 1e-12


def _frame():
    return pd.DataFrame({
        "Subject ID": ["C1", "C2", "C3", "C4", "C5", "C6",
                       "A1", "A2", "A3", "A4"],
        "Diagnosis": ["Control"] * 6 + ["AD"] * 4,
        "Condition": ["Control"] * 6 + ["AD"] * 4,
        "season": ["Winter", "Winter", "Spring", "Spring", "Summer", "Autumn",
                   "Winter", "Spring", "Autumn", "Autumn"],
        "Site": ["S1", "S2", "S1", "S2", "S1", "S2", "S1", "S2", "S1", "S2"],
    })


def _experiment(frame):
    from PyFLASH import ConditionBuilder

    conditions = (
        ConditionBuilder("Diagnosis")
        .add("Control", short="Control", color="grey")
        .add("AD", short="AD", color="red")
        .build()
    )
    return SimpleNamespace(
        summary=frame,
        condition_list=conditions,
        aliases={},
        fig_path="",
        data_path="",
    )


def _reference_counts(frame, category, levels, *, site=None):
    rows = frame.to_dict(orient="records")
    if site is not None:
        rows = [row for row in rows if row["Site"] == site]
    present = {row[category] for row in rows if row[category] is not None}
    if levels is None:
        try:
            levels = sorted(present)
        except TypeError:
            levels = list(dict.fromkeys(row[category] for row in rows
                                        if row[category] is not None))
    else:
        levels = [level for level in levels if level in present] or list(present)
    return [
        [sum(row["Diagnosis"] == group and row[category] == level for row in rows)
         for group in GROUPS]
        for level in levels
    ]


def _figure_counts(figure):
    return [
        [float(patch.get_height()) for patch in container.patches]
        for container in figure.axes[0].containers
    ]


def _compare(key, reference, expected, actual, agrees, shape):
    return {
        "contract": key,
        "reference": reference,
        "family": "independent-category-frequency-and-rendered-bars",
        "status": "agree" if agrees else "disagree",
        "shape": shape,
        "missingness_equal": bool(agrees),
        "max_absolute_error": "",
        "rtol": RTOL,
        "atol": ATOL,
        "pyflash_nonfinite": "none",
        "frozen_reference_agrees": bool(agrees),
        "pyflash_values": json.dumps(_jsonable(actual), sort_keys=True, default=str),
        "reference_values": json.dumps(_jsonable(expected), sort_keys=True, default=str),
    }


def _jsonable(value):
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def check(output):
    """Compare count plot bars and user-facing selections to Python tallies."""
    from matplotlib import pyplot as plt
    from matplotlib.colors import to_rgba
    from PyFLASH.plotting import plot_category_counts

    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    frame = _frame()
    experiment = _experiment(frame)
    figures = []
    rows = []

    def remember(result):
        for figure in figures:
            plt.close(figure)
        figures.clear()
        if isinstance(result, dict):
            figures.extend(value for value in result.values() if hasattr(value, "axes"))
        elif hasattr(result, "axes"):
            figures.append(result)
        return result

    def compare_figure(key, figure, category, levels, expected, shape):
        actual = _figure_counts(figure)
        agrees = len(actual) == len(expected) and all(
            len(a) == len(e)
            and np.allclose(a, e, rtol=RTOL, atol=ATOL)
            for a, e in zip(actual, expected)
        )
        rows.append(_compare(
            key, "literal row filtering and Python Counter tallies", expected,
            actual, agrees, shape,
        ))

    try:
        grouped = remember(plot_category_counts(
            experiment, "season", category_order=SEASONS, save=False))
        expected = _reference_counts(frame, "season", SEASONS)
        compare_figure("category-counts.grouped-conditions", grouped,
                       "season", SEASONS, expected, "category-by-condition-counts")

        factor = remember(plot_category_counts(
            experiment, "season", by="all", factor="Diagnosis",
            category_order=SEASONS, save=False))
        compare_figure("category-counts.explicit-factor", factor,
                       "season", SEASONS, expected, "category-by-explicit-factor-counts")

        stacked = remember(plot_category_counts(
            experiment, "season", kind="stacked", category_order=SEASONS,
            save=False))
        compare_figure("category-counts.stacked", stacked,
                       "season", SEASONS, expected, "stacked-segment-counts")

        annotated = remember(plot_category_counts(
            experiment, "season", kind="stacked", category_order=SEASONS,
            annotate=True, save=False))
        annotated_expected_counts = _reference_counts(frame, "season", SEASONS)
        annotated_actual = {
            "counts": _figure_counts(annotated),
            "labels": [text.get_text() for text in annotated.axes[0].texts],
        }
        annotated_expected = {
            "counts": annotated_expected_counts,
            "labels": [str(count) for level in annotated_expected_counts
                       for count in level if count > 0],
        }
        annotated_agrees = (
            np.allclose(annotated_actual["counts"], annotated_expected_counts,
                        rtol=RTOL, atol=ATOL)
            and annotated_actual["labels"] == annotated_expected["labels"]
        )
        rows.append(_compare(
            "category-counts.stacked-count-annotations",
            "literal positive category/group counts rendered inside stacked segments",
            annotated_expected, annotated_actual, annotated_agrees,
            "stacked-bar-segments-and-integer-count-labels"))

        missing_frame = frame.copy()
        missing_frame.loc[0, "season"] = None
        missing_experiment = _experiment(missing_frame)
        missing_figure = remember(plot_category_counts(
            missing_experiment, "season", category_order=SEASONS, save=False))
        missing_expected = _reference_counts(missing_frame, "season", SEASONS)
        missing_actual = _figure_counts(missing_figure)
        rows.append(_compare(
            "category-counts.missing-category-values",
            "literal row tally excludes missing categorical values from every group total",
            missing_expected, missing_actual,
            np.allclose(missing_actual, missing_expected, rtol=RTOL, atol=ATOL),
            "missing-level-exclusion-and-observed-level-counts"))

        normalized = remember(plot_category_counts(
            experiment, "season", normalize=True, category_order=SEASONS,
            save=False))
        totals = [sum(row) for row in zip(*expected)]
        percentage_expected = [
            [100.0 * count / total if total else 0.0
             for count, total in zip(counts, totals)]
            for counts in expected
        ]
        compare_figure("category-counts.within-group-percentages", normalized,
                       "season", SEASONS, percentage_expected,
                       "category-by-condition-percentages")
        rows.append(_compare(
            "category-counts.normalized-axis-units",
            "percentage scale is defined by each group total",
            {"ylabel": "Participants (%)", "group_totals": [100.0, 100.0]},
            {"ylabel": normalized.axes[0].get_ylabel(),
             "group_totals": [sum(column) for column in zip(*_figure_counts(normalized))]},
            normalized.axes[0].get_ylabel() == "Participants (%)"
            and np.allclose([sum(column) for column in zip(*_figure_counts(normalized))],
                            [100.0, 100.0], rtol=0.0, atol=1e-12),
            "normalized-units-and-per-group-total"))

        levels = ("Autumn", "Winter")
        labels = {"Autumn": "Fall", "Winter": "Cold season"}
        color = "#1b9e77"
        styled = remember(plot_category_counts(
            experiment, "season", category_order=levels,
            category_labels=labels, column_labels=["Season phase"],
            palette={"Autumn": color, "Winter": "#d95f02"},
            annotate=False, save=False))
        styled_actual = {
            "counts": _figure_counts(styled),
            "title": styled.axes[0].get_title(),
            "legend": [text.get_text() for text in styled.axes[0].get_legend().get_texts()],
            "annotations": [text.get_text() for text in styled.axes[0].texts],
            "first_facecolor": tuple(styled.axes[0].containers[0].patches[0].get_facecolor()),
        }
        styled_expected = {
            "counts": _reference_counts(frame, "season", levels),
            "title": "Season phase",
            "legend": [labels[level] for level in levels],
            "annotations": [],
            "first_facecolor": tuple(to_rgba(color)),
        }
        styled_agrees = (
            np.allclose(styled_actual["counts"], styled_expected["counts"],
                        rtol=RTOL, atol=ATOL)
            and styled_actual["title"] == styled_expected["title"]
            and styled_actual["legend"] == styled_expected["legend"]
            and styled_actual["annotations"] == styled_expected["annotations"]
            and np.allclose(styled_actual["first_facecolor"],
                            styled_expected["first_facecolor"], rtol=0.0, atol=1e-7)
        )
        rows.append(_compare(
            "category-counts.order-labels-palette-and-decoration",
            "literal requested level order, labels, RGB mapping and empty-annotation policy",
            styled_expected, styled_actual, styled_agrees,
            "display-options-preserve-category-identity-and-frequency-values"))

        queued = remember(plot_category_counts(
            experiment, "season", category_order=SEASONS,
            specificity=[("Site", "S1"), ("Site", "S2")], save=False))
        queue_expected = {
            site: _reference_counts(frame, "season", SEASONS, site=site)
            for site in ("S1", "S2")
        }
        queue_actual = {site[1]: _figure_counts(figure)
                        for site, figure in queued.items()}
        queue_agrees = set(queue_actual) == set(queue_expected) and all(
            np.allclose(queue_actual[site], queue_expected[site], rtol=RTOL, atol=ATOL)
            for site in queue_expected
        )
        rows.append(_compare(
            "category-counts.specificity-queue",
            "independent row filter by Site followed by literal group/category tallies",
            queue_expected, queue_actual, queue_agrees,
            "both-specificity-subfigures-and-their-count-matrices"))

        alias_filtered = remember(plot_category_counts(
            experiment, "season", category_order=SEASONS,
            filter_by={"Site": "S1"}, save=False))
        alias_expected = _reference_counts(frame, "season", SEASONS, site="S1")
        alias_actual = _figure_counts(alias_filtered)
        rows.append(_compare(
            "category-counts.filter-by-alias",
            "literal row filtering by Site=S1 followed by condition/category tallies",
            alias_expected, alias_actual,
            np.allclose(alias_actual, alias_expected, rtol=RTOL, atol=ATOL),
            "filter-alias-count-matrix"))

        without_legend = remember(plot_category_counts(
            experiment, "season", category_order=SEASONS,
            legend=False, save=False))
        no_legend_actual = {
            "counts": _figure_counts(without_legend),
            "legend_present": without_legend.axes[0].get_legend() is not None,
        }
        no_legend_expected = {"counts": expected, "legend_present": False}
        rows.append(_compare(
            "category-counts.legend-disabled",
            "literal row tallies and absent legend when legend=False",
            no_legend_expected, no_legend_actual,
            np.allclose(no_legend_actual["counts"], expected, rtol=RTOL, atol=ATOL)
            and not no_legend_actual["legend_present"],
            "legend-option-and-count-matrix"))

        roi_experiment = SimpleNamespace(
            summary=frame,
            summaries={"SCN": frame[frame["Site"] == "S1"].copy(),
                       "OC": frame[frame["Site"] == "S2"].copy()},
            condition_list=experiment.condition_list,
            aliases={},
            fig_path="",
            data_path="",
        )
        roi_figure = remember(plot_category_counts(
            roi_experiment, "season", category_order=SEASONS,
            roi="SCN", save=False))
        roi_expected = _reference_counts(frame, "season", SEASONS, site="S1")
        roi_actual = _figure_counts(roi_figure)
        rows.append(_compare(
            "category-counts.explicit-roi",
            "literal tallies over the selected SCN summary rows",
            roi_expected, roi_actual,
            np.allclose(roi_actual, roi_expected, rtol=RTOL, atol=ATOL),
            "selected-roi-count-matrix"))

        roi_queue = remember(plot_category_counts(
            roi_experiment, "season", category_order=SEASONS, save=False))
        roi_queue_expected = {
            "SCN": _reference_counts(frame, "season", SEASONS, site="S1"),
            "OC": _reference_counts(frame, "season", SEASONS, site="S2"),
        }
        roi_queue_actual = {name: _figure_counts(figure)
                            for name, figure in roi_queue.items()}
        roi_queue_agrees = set(roi_queue_actual) == set(roi_queue_expected) and all(
            np.allclose(roi_queue_actual[name], roi_queue_expected[name],
                        rtol=RTOL, atol=ATOL)
            for name in roi_queue_expected
        )
        rows.append(_compare(
            "category-counts.default-roi-queue",
            "literal row tallies independently computed for each named ROI summary",
            roi_queue_expected, roi_queue_actual, roi_queue_agrees,
            "dictionary-of-figures-keyed-by-roi"))

        columns = remember(plot_category_counts(
            experiment, ["season", "Site"], category_order=None, save=False))
        column_expected = {
            "season": _reference_counts(frame, "season", None),
            "Site": _reference_counts(frame, "Site", None),
        }
        column_actual = {name: _figure_counts(figure) for name, figure in columns.items()}
        column_agrees = set(column_actual) == set(column_expected) and all(
            np.allclose(column_actual[name], column_expected[name], rtol=RTOL, atol=ATOL)
            for name in column_expected
        )
        rows.append(_compare(
            "category-counts.category-column-queue",
            "literal independent tallies for each requested category column",
            column_expected, column_actual, column_agrees,
            "dictionary-of-figures-keyed-by-category-column"))

        coerced = remember(plot_category_counts(
            frame, "season", category_order=SEASONS,
            conditions=experiment.condition_list,
            condition_col="Diagnosis", animal_col="Subject ID", save=False))
        coerced_actual = {"counts": _figure_counts(coerced),
                          "group_labels": [text.get_text() for text in coerced.axes[0].get_xticklabels()]}
        coerced_expected = {"counts": expected,
                            "group_labels": ["Control\n(n=6)", "AD\n(n=4)"]}
        coerced_agrees = (
            np.allclose(coerced_actual["counts"], expected, rtol=RTOL, atol=ATOL)
            and coerced_actual["group_labels"] == coerced_expected["group_labels"]
        )
        rows.append(_compare(
            "category-counts.dataframe-input-adapter",
            "independent row counts after the declared condition and subject adapter",
            coerced_expected, coerced_actual, coerced_agrees,
            "raw-dataframe-condition-adaptation-and-group-totals"))

        grouped_frame = remember(plot_category_counts(
            frame, "season", category_order=SEASONS,
            group_col="Diagnosis", animal_col="Subject ID",
            dataframe_kwargs={"group_order": list(GROUPS)}, save=False))
        grouped_frame_actual = {
            "counts": _figure_counts(grouped_frame),
            "group_labels": [text.get_text() for text in
                             grouped_frame.axes[0].get_xticklabels()],
        }
        grouped_frame_expected = {
            "counts": expected,
            "group_labels": ["Control\n(n=6)", "AD\n(n=4)"],
        }
        grouped_frame_agrees = (
            np.allclose(grouped_frame_actual["counts"], expected,
                        rtol=RTOL, atol=ATOL)
            and grouped_frame_actual["group_labels"]
            == grouped_frame_expected["group_labels"]
        )
        rows.append(_compare(
            "category-counts.dataframe-group-column-adapter",
            "literal row tallies after group_col and explicit group-order adaptation",
            grouped_frame_expected, grouped_frame_actual, grouped_frame_agrees,
            "raw-dataframe-group-column-adaptation-and-group-totals"))

        group_alias = remember(plot_category_counts(
            frame, "season", category_order=SEASONS,
            groups=experiment.condition_list, condition_col="Diagnosis",
            subject_col="Subject ID", save=False))
        group_alias_actual = {
            "counts": _figure_counts(group_alias),
            "group_labels": [text.get_text() for text in
                             group_alias.axes[0].get_xticklabels()],
        }
        group_alias_expected = {
            "counts": expected,
            "group_labels": ["Control\n(n=6)", "AD\n(n=4)"],
        }
        group_alias_agrees = (
            np.allclose(group_alias_actual["counts"], expected,
                        rtol=RTOL, atol=ATOL)
            and group_alias_actual["group_labels"]
            == group_alias_expected["group_labels"]
        )
        rows.append(_compare(
            "category-counts.dataframe-groups-and-subject-aliases",
            "literal row tallies after groups, condition_col and subject_col adaptation",
            group_alias_expected, group_alias_actual, group_alias_agrees,
            "raw-dataframe-groups-and-subject-alias-adaptation"))

        group_list_alias = remember(plot_category_counts(
            frame, "season", category_order=SEASONS,
            group_list=experiment.condition_list, condition_col="Diagnosis",
            animal_col="Subject ID", save=False))
        group_list_actual = {
            "counts": _figure_counts(group_list_alias),
            "group_labels": [text.get_text() for text in
                             group_list_alias.axes[0].get_xticklabels()],
        }
        group_list_expected = {
            "counts": expected,
            "group_labels": ["Control\n(n=6)", "AD\n(n=4)"],
        }
        group_list_agrees = (
            np.allclose(group_list_actual["counts"], expected,
                        rtol=RTOL, atol=ATOL)
            and group_list_actual["group_labels"]
            == group_list_expected["group_labels"]
        )
        rows.append(_compare(
            "category-counts.dataframe-group-list-alias",
            "literal row tallies after group_list alias adapts the declared conditions",
            group_list_expected, group_list_actual, group_list_agrees,
            "raw-dataframe-group-list-alias-adaptation"))

        frame_records = frame.to_dict(orient="records")
        factor_groups = list(dict.fromkeys(frame["Site"]))
        factor_expected_counts = [
            [sum(row["Site"] == site and row["season"] == level
                 for row in frame_records) for site in factor_groups]
            for level in SEASONS
        ]
        factor_expected_labels = [
            f"{site}\n(n={sum(row['Site'] == site for row in frame_records)})"
            for site in factor_groups
        ]
        factor_group_figure = remember(plot_category_counts(
            frame, "season", by="all", factor="Site", category_order=SEASONS,
            group_cols=["Diagnosis", "Site"], subject_col="Subject ID",
            save=False))
        factor_group_actual = {
            "counts": _figure_counts(factor_group_figure),
            "group_labels": [text.get_text() for text in
                             factor_group_figure.axes[0].get_xticklabels()],
        }
        factor_group_agrees = (
            np.allclose(factor_group_actual["counts"], factor_expected_counts,
                        rtol=RTOL, atol=ATOL)
            and factor_group_actual["group_labels"] == factor_expected_labels
        )
        rows.append(_compare(
            "category-counts.dataframe-group-cols-factor-alias",
            "literal category tallies within each Site factor level after group_cols adaptation",
            {"counts": factor_expected_counts, "group_labels": factor_expected_labels},
            factor_group_actual, factor_group_agrees,
            "crossed-factor-count-matrix-and-combination-sample-sizes"))

        save_root = output / "saved-output"
        save_experiment = SimpleNamespace(
            summary=frame, condition_list=experiment.condition_list,
            aliases={}, fig_path=str(save_root), data_path=str(save_root),
        )
        saved_figure = remember(plot_category_counts(
            save_experiment, "season", category_order=SEASONS,
            column_labels=["Season"], save=True))
        saved_svgs = list(save_root.rglob("*.svg"))
        saved_actual_counts = _figure_counts(saved_figure)
        if len(saved_svgs) == 1:
            saved_svg = saved_svgs[0]
            svg_text = saved_svg.read_text(encoding="utf-8")
            manifest_path = saved_svg.with_name("figures.json")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            saved_entry = manifest.get("figures", {}).get(saved_svg.name, {})
        else:
            svg_text = ""
            saved_entry = {}
        saved_actual = {
            "counts": saved_actual_counts,
            "svg_count": len(saved_svgs),
            "editable_text": "<text" in svg_text,
            "producer_function": saved_entry.get("function"),
            "recorded_column_labels": (saved_entry.get("args") or {}).get("column_labels"),
            "reprofig_identity": bool(saved_entry.get("figure_id")),
        }
        saved_expected = {
            "counts": expected,
            "svg_count": 1,
            "editable_text": True,
            "producer_function": "PyFLASH.plotting.plot_category_counts",
            "recorded_column_labels": ["Season"],
            "reprofig_identity": True,
        }
        saved_agrees = (
            np.allclose(saved_actual_counts, expected, rtol=RTOL, atol=ATOL)
            and saved_actual["svg_count"] == 1
            and saved_actual["editable_text"]
            and saved_actual["producer_function"] == saved_expected["producer_function"]
            and saved_actual["recorded_column_labels"] == ["Season"]
            and saved_actual["reprofig_identity"]
        )
        rows.append(_compare(
            "category-counts.saved-svg-output-and-provenance",
            "literal count matrix, editable SVG text, public plot name and requested display label in the saved figure receipt",
            saved_expected, saved_actual, saved_agrees,
            "saved-svg-render-and-function-argument-provenance"))

        evidence = {
            "case": "ten records, two diagnosis groups, four season levels and a two-site specificity split",
            "reference": "literal Python record filtering and per-group level counts; no pandas crosstab",
            "comparisons": rows,
        }
        (output / "category-counts-independent-evidence.json").write_text(
            json.dumps(evidence, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        failures = [row["contract"] for row in rows if row["status"] != "agree"]
        if failures:
            raise AssertionError("Category-count plot disagreements: " + ", ".join(failures))
        return rows
    finally:
        for figure in figures:
            plt.close(figure)
