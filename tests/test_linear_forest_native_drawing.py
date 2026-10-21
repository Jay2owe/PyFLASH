"""Public precomputed-coefficient drawing against authenticated native answers.

These checks qualify the executed input/selection/drawing options. They do not
certify the parent estimator, every scientific plot or whole-package coverage.
No figure is saved; complete native coordinates are inspected on the live axes.
"""
from copy import deepcopy
import json
from types import SimpleNamespace

import matplotlib

# Inspect scientific artists without launching a desktop window. Browser and
# native export verification retain their separate real-renderer checks.
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from PyFLASH.plotting import plot_linear_model_coefficient_forest
from reproducibility import linear_parent_contract as native
from reproducibility.linear_forest_contract import (
    assert_native_marks, cases, draw, native_table,
)


NATIVE_ROWS = cases()


@pytest.fixture(scope="module", autouse=True)
def authenticated_original_answers():
    native.check_identity()


def ordinary_row():
    return next(row for row in NATIVE_ROWS
                if row["case"]["key"] == "linear-parent.HAC.lag-0.correction-false")


@pytest.mark.parametrize("row", NATIVE_ROWS, ids=lambda row: row["case"]["key"])
def test_full_native_estimates_intervals_and_probability_colors(row):
    before = deepcopy(row)
    table = native_table(row)
    original = table.copy(deep=True)
    result = draw(table)
    try:
        assert_native_marks(result["figure"], table[table.term != "Intercept"])
        pd.testing.assert_frame_equal(result["coefficients"], original)
        pd.testing.assert_frame_equal(table, original)
        assert result["path"] is None
        assert result["figure"].axes[0].get_title() == "Linear model coefficients (p value, alpha=0.05)"
    finally:
        plt.close(result["figure"])
    assert row == before


def test_coefficient_labels_apply_without_changing_native_values_or_leaking():
    table = native_table(ordinary_row())
    original = table.copy(deep=True)
    renamed = draw(table, dependent_variables="y", terms=["x"],
                   column_labels={"y": "Response", "x": "Predictor"})
    ordinary = draw(table, dependent_variables="y", terms=["x"])
    try:
        assert [tick.get_text() for tick in renamed["figure"].axes[0].get_yticklabels()] == ["Response: Predictor"]
        assert [tick.get_text() for tick in ordinary["figure"].axes[0].get_yticklabels()] == ["y: x"]
        expected = table[(table.dependent_variable == "y") & (table.term == "x")]
        assert_native_marks(renamed["figure"], expected)
        assert_native_marks(ordinary["figure"], expected)
        pd.testing.assert_frame_equal(renamed["coefficients"], expected)
        pd.testing.assert_frame_equal(table, original)
    finally:
        plt.close(renamed["figure"])
        plt.close(ordinary["figure"])


def test_categorical_coefficient_labels_preserve_native_term_identity():
    table = native_table(ordinary_row())
    selected = table[(table.dependent_variable == "y") & (table.term == "gB")].copy()
    selected["term"] = "C(g, Treatment(reference='A'))[T.B]"
    original = selected.copy(deep=True)
    result = draw(selected, column_labels={"g": "Group", "y": "Response"})
    try:
        assert [tick.get_text() for tick in result["figure"].axes[0].get_yticklabels()] == ["Response: Group: B"]
        assert_native_marks(result["figure"], original)
        pd.testing.assert_frame_equal(result["coefficients"], original)
        pd.testing.assert_frame_equal(selected, original)
    finally:
        plt.close(result["figure"])


def test_failed_labeled_selection_does_not_leak_labels_into_the_next_plot():
    table = native_table(ordinary_row())
    with pytest.raises(ValueError, match="No coefficient rows remain"):
        draw(table, terms="no-such-term", column_labels={"y": "Response", "x": "Predictor"})
    result = draw(table, dependent_variables="y", terms="^x$")
    try:
        assert [tick.get_text() for tick in result["figure"].axes[0].get_yticklabels()] == ["y: x"]
        assert_native_marks(result["figure"], table[(table.dependent_variable == "y") & (table.term == "x")])
    finally:
        plt.close(result["figure"])


@pytest.mark.parametrize("source_form", ["dataframe", "records", "mapping", "attribute", "csv-path", "csv-coefficients", "csv-experiment", "experiment-dataframe"])
def test_native_drawing_matches_supported_table_sources(source_form, tmp_path):
    table = native_table(ordinary_row())
    original = table.copy(deep=True)
    options = {}
    supplied = table
    if source_form == "records":
        supplied = table.to_dict("records")
    elif source_form in {"mapping", "attribute"}:
        supplied = None
        options = {"experiment": {"qualified": table} if source_form == "mapping"
                   else SimpleNamespace(qualified=table), "table_attr": "qualified"}
    elif source_form.startswith("csv-"):
        path = tmp_path / "native-coefficients.csv"
        table.to_csv(path, index=False)
        if source_form == "csv-path":
            supplied = None
            options = {"path": path}
        elif source_form == "csv-coefficients":
            supplied = path
        else:
            supplied = None
            options = {"experiment": path}
    elif source_form == "experiment-dataframe":
        supplied = None
        options = {"experiment": table}
    result = draw(supplied, **options)
    try:
        assert_native_marks(result["figure"], table[table.term != "Intercept"])
        np.testing.assert_allclose(result["coefficients"].estimate, table.estimate,
                                   rtol=1e-9, atol=1e-12)
        assert result["coefficients"].term.tolist() == table.term.tolist()
        assert result["coefficients"].dependent_variable.tolist() == table.dependent_variable.tolist()
        pd.testing.assert_frame_equal(table, original)
    finally:
        plt.close(result["figure"])


@pytest.mark.parametrize("gate", ["p", "p_value", "q", "q_value", "fdr", "Q"])
@pytest.mark.parametrize("alpha", [.01, .05, .1])
def test_supplied_native_probabilities_determine_all_point_colors(gate, alpha):
    table = native_table(ordinary_row())
    result = draw(table, gate=gate, alpha=alpha)
    try:
        column = "q_value" if gate.lower() in {"q", "q_value", "fdr"} else "p_value"
        assert_native_marks(result["figure"], table[table.term != "Intercept"],
                            gate=column, alpha=alpha)
        assert result["figure"].axes[0].get_title() == f"Linear model coefficients ({'q value' if column == 'q_value' else 'p value'}, alpha={alpha:g})"
    finally:
        plt.close(result["figure"])


def test_absent_corrected_probability_column_preserves_native_p_value_fallback():
    table = native_table(ordinary_row()).drop(columns="q_value")
    result = draw(table, gate="q")
    try:
        assert_native_marks(result["figure"], table[table.term != "Intercept"])
        assert result["figure"].axes[0].get_title() == "Linear model coefficients (p value, alpha=0.05)"
    finally:
        plt.close(result["figure"])


@pytest.mark.parametrize("terms", ["^x$", ["x"], ("x",)])
@pytest.mark.parametrize("endpoints", ["y", ["y2", "y"]])
def test_endpoint_and_term_selection_preserve_native_coordinates(terms, endpoints):
    table = native_table(ordinary_row())
    result = draw(table, terms=terms, dependent_variables=endpoints)
    try:
        wanted = [endpoints] if isinstance(endpoints, str) else endpoints
        selected = table[(table.term == "x") & table.dependent_variable.isin(wanted)]
        expected = pd.concat([selected[selected.dependent_variable == endpoint] for endpoint in wanted])
        assert_native_marks(result["figure"], expected)
        assert [tick.get_text() for tick in result["figure"].axes[0].get_yticklabels()] == [endpoint + ": x" for endpoint in wanted[::-1]]
        pd.testing.assert_frame_equal(result["coefficients"], selected)
    finally:
        plt.close(result["figure"])


@pytest.mark.parametrize("limit", [1, 3, 60])
@pytest.mark.parametrize("title", ["auto", "Specified title", None, False])
def test_term_limit_and_title_preserve_selected_native_values(limit, title):
    table = native_table(ordinary_row())
    result = draw(table, max_terms=limit, title=title, tick_label_size=11)
    try:
        expected = table[table.term != "Intercept"].iloc[:limit]
        assert_native_marks(result["figure"], expected)
        ax = result["figure"].axes[0]
        assert ax.get_title() == ("Linear model coefficients (p value, alpha=0.05)"
                                 if title == "auto" else title or "")
        omitted = len(table[table.term != "Intercept"]) - len(expected)
        assert [text.get_text() for text in ax.texts] == ([f"{omitted} further term(s) omitted"] if omitted else [])
        assert all(tick.get_fontsize() == 11 for tick in ax.get_yticklabels())
        pd.testing.assert_frame_equal(result["coefficients"], table)
    finally:
        plt.close(result["figure"])


@pytest.mark.parametrize("options, message", [
    ({"dependent_variables": "absent"}, "No coefficient rows remain"),
    ({"terms": []}, "terms must not be empty"),
    ({"terms": "no-such-term"}, "No coefficient rows remain"),
    ({"terms": "["}, "not a valid pattern"),
])
def test_invalid_selections_refuse_without_changing_input(options, message):
    table = native_table(ordinary_row())
    original = table.copy(deep=True)
    with pytest.raises(ValueError, match=message):
        draw(table, **options)
    pd.testing.assert_frame_equal(table, original)


@pytest.mark.parametrize("mark", ["estimate", "interval"])
def test_native_coordinate_checks_reject_changed_drawn_marks(mark):
    table = native_table(ordinary_row())
    result = draw(table)
    try:
        ax, = result["figure"].axes
        if mark == "estimate":
            points = ax.collections[-1].get_offsets().copy()
            points[0, 0] += 1
            ax.collections[-1].set_offsets(points)
        else:
            segments = ax.collections[0].get_segments()
            segments[0][0, 0] += 1
            ax.collections[0].set_segments(segments)
        with pytest.raises(AssertionError):
            assert_native_marks(result["figure"], table[table.term != "Intercept"])
    finally:
        plt.close(result["figure"])


def test_native_drawing_family_is_registered_with_partial_scope():
    from reproducibility import linear_forest_contract as contract
    from reproducibility.validation_registry import FAMILIES
    assert FAMILIES["public-linear-coefficient-drawing"] == contract.__name__
    assert contract.COMPLETE_CONTRACT is False
    assert len(contract.cases()) == 47


def test_registered_drawing_family_retains_complete_json_paired_marks(monkeypatch, tmp_path):
    from reproducibility import linear_forest_contract as contract
    row = ordinary_row()
    monkeypatch.setattr(contract, "cases", lambda: [row])
    monkeypatch.setattr(contract, "uncertainty_cases", lambda: [])
    monkeypatch.setattr(contract, "probability_cases", lambda: [])
    comparisons = contract.validate(tmp_path)
    assert len(comparisons) == 1 and comparisons[0]["status"] == "agree"
    text = (tmp_path / "linear-forest-native-paired.json").read_text(encoding="utf-8")
    assert "NaN" not in text and "Infinity" not in text
    paired = json.loads(text)
    assert paired["complete_contract"] is False
    observed = paired["rows"][0]["observed"]
    assert observed["actual_zero_line"] == [0, 0]
    assert len(observed["actual_points"]) == len(observed["actual_interval_segments"]) == 8
    assert paired["rows"][0]["original_native_answers"] == row["expected"]
    assert all(item["q_value"] is None for item in observed["native_table"] if item["term"] == "Intercept")
