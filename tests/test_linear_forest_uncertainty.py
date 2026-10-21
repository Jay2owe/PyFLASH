"""Supplied interval identity and missingness in the public coefficient forest.

The estimate and probability originate in authenticated native answers. Interval
variants are literal client-input controls, not new independently fitted answers.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from reproducibility import linear_forest_contract as reference


@pytest.fixture(scope="module", autouse=True)
def authenticated_native_answers():
    reference.check_identity()


def one_native_coefficient():
    row = next(row for row in reference.cases()
               if row["case"]["key"] == "linear-parent.HAC.lag-0.correction-false")
    table = reference.native_table(row)
    return table[(table.dependent_variable == "y") & (table.term == "x")].copy()


def drawn_intervals(ax):
    # The final collection is the coefficient point; the preceding collections
    # contain actual confidence-interval line segments, never inferred values.
    return [segment for collection in ax.collections[:-1]
            for segment in collection.get_segments() if len(segment)]


@pytest.mark.parametrize("missing", [("ci_low",), ("ci_high",), ("ci_low", "ci_high")])
def test_unknown_interval_does_not_become_a_zero_width_or_one_sided_interval(missing):
    table = one_native_coefficient()
    for field in missing:
        table[field] = np.nan
    before = table.copy(deep=True)
    result = reference.draw(table)
    try:
        ax, = result["figure"].axes
        assert drawn_intervals(ax) == []
        np.testing.assert_array_equal(ax.collections[-1].get_offsets(), [[table.estimate.iloc[0], 0]])
        pd.testing.assert_frame_equal(table, before)
        pd.testing.assert_frame_equal(result["coefficients"], before)
    finally:
        plt.close(result["figure"])


@pytest.mark.parametrize("offsets", [(1., 2.), (-2., -1.)])
def test_supplied_ordered_interval_is_drawn_when_it_does_not_contain_the_estimate(offsets):
    table = one_native_coefficient()
    estimate = table.estimate.iloc[0]
    table["ci_low"] = estimate + offsets[0]
    table["ci_high"] = estimate + offsets[1]
    before = table.copy(deep=True)
    result = reference.draw(table)
    try:
        ax, = result["figure"].axes
        intervals = drawn_intervals(ax)
        assert len(intervals) == 1
        np.testing.assert_array_equal(intervals[0], [[table.ci_low.iloc[0], 0], [table.ci_high.iloc[0], 0]])
        np.testing.assert_array_equal(ax.collections[-1].get_offsets(), [[estimate, 0]])
        pd.testing.assert_frame_equal(table, before)
        pd.testing.assert_frame_equal(result["coefficients"], before)
    finally:
        plt.close(result["figure"])


def test_known_zero_width_supplied_interval_remains_defined():
    table = one_native_coefficient()
    estimate = table.estimate.iloc[0]
    table["ci_low"] = table["ci_high"] = estimate
    result = reference.draw(table)
    try:
        ax, = result["figure"].axes
        interval, = drawn_intervals(ax)
        np.testing.assert_array_equal(interval, [[estimate, 0], [estimate, 0]])
    finally:
        plt.close(result["figure"])


def test_supplied_interval_remains_available_when_only_the_point_is_missing():
    table = one_native_coefficient()
    low, high = table.ci_low.iloc[0], table.ci_high.iloc[0]
    table["estimate"] = np.nan
    result = reference.draw(table)
    try:
        ax, = result["figure"].axes
        interval, = drawn_intervals(ax)
        np.testing.assert_array_equal(interval, [[low, 0], [high, 0]])
        assert np.ma.getmaskarray(ax.collections[-1].get_offsets()).all()
    finally:
        plt.close(result["figure"])


def test_reversed_supplied_interval_is_refused_without_mutating_the_table():
    table = one_native_coefficient()
    table["ci_low"], table["ci_high"] = table.ci_high.copy(), table.ci_low.copy()
    before = table.copy(deep=True)
    with pytest.raises(ValueError, match="lower bounds must not exceed upper bounds"):
        reference.draw(table)
    pd.testing.assert_frame_equal(table, before)


@pytest.mark.parametrize("name", reference.uncertainty_cases())
def test_registered_uncertainty_observation_preserves_the_supplied_values(name):
    observed = reference.observe_uncertainty(name)
    assert len(observed['supplied_table']) == 1


@pytest.mark.parametrize("row", reference.cases(), ids=lambda row: row["case"]["key"])
def test_report_contains_the_complete_original_native_coefficient_values(row):
    from PyFLASH import report
    from PyFLASH.plotting import plot_linear_model_coefficient_forest
    table = reference.native_table(row)
    before = table.copy(deep=True)
    report.start()
    result = None
    try:
        result = plot_linear_model_coefficient_forest(
            coefficients=table, save=False, return_data=True, emit_report=True)
        records = report.collect()
        expected_endpoints = list(dict.fromkeys(table.dependent_variable))
        assert [record["dependent_variable"] for record in records] == expected_endpoints
        for record in records:
            assert record["kind"] == "linear_model"
            expected = table[table.dependent_variable == record["dependent_variable"]]
            assert set(record["coefficients"]) == set(expected.term)
            for value in expected.itertuples(index=False):
                actual = record["coefficients"][value.term]
                for field, source in [("estimate", "estimate"), ("p", "p_value"),
                                      ("q", "q_value"), ("ci_low", "ci_low"),
                                      ("ci_high", "ci_high")]:
                    native_value = getattr(value, source)
                    assert actual[field] == (None if pd.isna(native_value) else native_value)
        pd.testing.assert_frame_equal(table, before)
        pd.testing.assert_frame_equal(result["coefficients"], before)
    finally:
        report.collect()
        if result is not None:
            plt.close(result["figure"])


def test_missing_report_bounds_are_unknown_and_suppressed_reports_emit_nothing():
    from PyFLASH import report
    from PyFLASH.plotting import plot_linear_model_coefficient_forest
    table = one_native_coefficient()
    table["ci_low"] = table["ci_high"] = np.nan
    for enabled in [True, False]:
        report.start()
        result = None
        try:
            result = plot_linear_model_coefficient_forest(
                coefficients=table, save=False, return_data=True, emit_report=enabled)
            records = report.collect()
            if enabled:
                coefficient = records[0]["coefficients"]["x"]
                assert coefficient["ci_low"] is coefficient["ci_high"] is None
                assert coefficient["estimate"] == table.estimate.iloc[0]
            else:
                assert records == []
        finally:
            report.collect()
            if result is not None:
                plt.close(result["figure"])
