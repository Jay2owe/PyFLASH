"""Partial public coefficient-forest drawing from authenticated native tables.

The drawing performs no fitting: each estimate, interval and probability comes
from the unchanged native linear reference fixture. Compare its complete live
scientific artists, input ownership and literal supplied term identities. Save
full paired data for later inspection without exporting a figure or refitting.
This does not certify every plot/output option or the parent linear estimator.
"""
from pathlib import Path

from reproducibility import linear_parent_contract as native

CAPABILITY = "linear_model_coefficient_forest"
COMPLETE_CONTRACT = False
PREFIX = "linear-forest-native."


def cases():
    return [row for row in native.cases()
            if "expected_domain_error" not in row["case"]]


def check_identity():
    return native.check_identity()


def native_table(row):
    import pandas as pd
    records = []
    for endpoint, output in row["expected"].items():
        for term, fields in output["coefficients"].items():
            records.append({"dependent_variable": endpoint,
                            "term": "Intercept" if term == "(Intercept)" else term,
                            **fields})
    return pd.DataFrame(records)


def draw(table=None, *, emit_report=False, **options):
    from PyFLASH.plotting import plot_linear_model_coefficient_forest
    return plot_linear_model_coefficient_forest(
        coefficients=table, save=False, return_data=True, emit_report=emit_report,
        **options)


def assert_native_report(records, table):
    """Check report transport against literal supplied native rows, without fits."""
    import pandas as pd
    assert [record['dependent_variable'] for record in records] == list(dict.fromkeys(table.dependent_variable))
    for record in records:
        assert record['kind'] == 'linear_model'
        selected = table[table.dependent_variable == record['dependent_variable']]
        assert set(record['coefficients']) == set(selected.term)
        for value in selected.itertuples(index=False):
            actual = record['coefficients'][value.term]
            for field, source in [('estimate', 'estimate'), ('p', 'p_value'),
                                  ('q', 'q_value'), ('ci_low', 'ci_low'),
                                  ('ci_high', 'ci_high')]:
                original = getattr(value, source)
                assert actual[field] == (None if pd.isna(original) else original)


def uncertainty_cases():
    return ['missing-lower', 'missing-upper', 'missing-both', 'outside-above',
            'outside-below', 'defined-zero-width', 'missing-estimate', 'reversed-bounds']


def probability_cases():
    """Literal public selector choices; no new independently fitted answers."""
    return [(gate, column) for gate, column in [
        ('p', 'p_value'), ('p_value', 'p_value'), (' P ', 'p_value'),
        ('q', 'q_value'), ('q_value', 'q_value'), ('fdr', 'q_value'),
        (' Q ', 'q_value'), (' q_value ', 'q_value'), (' FDR ', 'q_value'),
        ('unrecognized', None), ('qq', None)]]


def observe_probability(gate, column):
    """Pair native probabilities with actual color, title and report transport."""
    import matplotlib.colors as colors
    import matplotlib.pyplot as plt
    import pandas as pd
    from PyFLASH import report
    table = uncertainty_table('defined-zero-width')
    original = table.copy(deep=True)
    p, q = table.p_value.iloc[0], table.q_value.iloc[0]
    assert 0 <= p < q <= 1
    alpha = float((p + q) / 2)
    result = None
    figures_before = plt.get_fignums()
    report.start()
    try:
        if column is None:
            try:
                result = draw(table, gate=gate, alpha=alpha, emit_report=True)
            except ValueError as error:
                assert 'gate' in str(error)
                assert report.collect() == []
                assert plt.get_fignums() == figures_before
                pd.testing.assert_frame_equal(table, original)
                return {'selector': gate, 'alpha': alpha,
                        'supplied_table': original.to_dict('records'),
                        'refused': str(error), 'actual_report_records': []}
            raise AssertionError('Unknown probability selector was accepted')
        result = draw(table, gate=gate, alpha=alpha, emit_report=True)
        records = report.collect()
        assert_native_report(records, original)
        ax, = result['figure'].axes
        assert_native_marks(result['figure'], original, gate=column, alpha=alpha)
        wanted = colors.to_rgba('#C43C39' if original[column].iloc[0] < alpha else '#606060')
        assert ax.collections[-1].get_facecolors().tolist() == [list(wanted)]
        assert ('q value' if column == 'q_value' else 'p value') in ax.get_title()
        pd.testing.assert_frame_equal(table, original)
        pd.testing.assert_frame_equal(result['coefficients'], original)
        return {'selector': gate, 'selected_column': column, 'alpha': alpha,
                'supplied_table': original.to_dict('records'),
                'actual_point_rgba': ax.collections[-1].get_facecolors().tolist(),
                'actual_title': ax.get_title(), 'actual_report_records': records}
    finally:
        report.collect()
        if result is not None:
            plt.close(result['figure'])


def uncertainty_table(name):
    """Literal client-input variants; these are not new independently fitted answers."""
    import numpy as np
    row = next(row for row in cases()
               if row['case']['key'] == 'linear-parent.HAC.lag-0.correction-false')
    table = native_table(row)
    table = table[(table.dependent_variable == 'y') & (table.term == 'x')].copy()
    estimate = table.estimate.iloc[0]
    if name in {'missing-lower', 'missing-both'}:
        table['ci_low'] = np.nan
    if name in {'missing-upper', 'missing-both'}:
        table['ci_high'] = np.nan
    if name == 'outside-above':
        table['ci_low'], table['ci_high'] = estimate + 1., estimate + 2.
    if name == 'outside-below':
        table['ci_low'], table['ci_high'] = estimate - 2., estimate - 1.
    if name == 'defined-zero-width':
        table['ci_low'] = table['ci_high'] = estimate
    if name == 'missing-estimate':
        table['estimate'] = np.nan
    if name == 'reversed-bounds':
        table['ci_low'], table['ci_high'] = table.ci_high.copy(), table.ci_low.copy()
    assert name in uncertainty_cases()
    return table


def observe_uncertainty(name):
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    from PyFLASH import report
    table = uncertainty_table(name)
    original = table.copy(deep=True)
    result = None
    report.start()
    try:
        if name == 'reversed-bounds':
            try:
                result = draw(table, emit_report=True)
            except ValueError as error:
                assert 'lower bounds must not exceed upper bounds' in str(error)
                assert report.collect() == []
                pd.testing.assert_frame_equal(table, original)
                return {'supplied_table': table.to_dict('records'), 'refused': str(error),
                        'actual_report_records': []}
            raise AssertionError('Reversed endpoints were accepted')
        result = draw(table, emit_report=True)
        records = report.collect()
        assert_native_report(records, original)
        ax, = result['figure'].axes
        segments = [segment for collection in ax.collections[:-1]
                    for segment in collection.get_segments() if len(segment)]
        if name.startswith('missing-') and name != 'missing-estimate':
            assert segments == []
        else:
            assert len(segments) == 1
            np.testing.assert_array_equal(segments[0],
                [[table.ci_low.iloc[0], 0], [table.ci_high.iloc[0], 0]])
        points = ax.collections[-1].get_offsets()
        point_mask = np.ma.getmaskarray(points)
        if name == 'missing-estimate':
            assert point_mask.all()
        else:
            assert not point_mask.any()
            np.testing.assert_array_equal(points, [[table.estimate.iloc[0], 0]])
        pd.testing.assert_frame_equal(table, original)
        pd.testing.assert_frame_equal(result['coefficients'], original)
        return {'supplied_table': original.to_dict('records'),
                'actual_points': points.filled(np.nan).tolist(),
                'actual_point_mask': point_mask.tolist(),
                'actual_interval_segments': [segment.tolist() for segment in segments],
                'actual_report_records': records}
    finally:
        report.collect()
        if result is not None:
            plt.close(result['figure'])


def assert_native_marks(fig, expected, *, gate="p_value", alpha=.05):
    """Compare actual artist operands with the original native coordinates."""
    import matplotlib.colors as colors
    import numpy as np
    import pandas as pd
    ax, = fig.axes
    expected = expected.iloc[::-1]
    y = np.arange(len(expected), dtype=float)
    points = ax.collections[-1]
    np.testing.assert_allclose(points.get_offsets(),
        np.column_stack((expected["estimate"].to_numpy(float), y)),
        rtol=1e-9, atol=1e-12, equal_nan=True)
    segments = ax.collections[0].get_segments()
    assert len(segments) == len(expected)
    for index, (_, row) in enumerate(expected.iterrows()):
        if np.isfinite([row["estimate"], row["ci_low"], row["ci_high"]]).all():
            np.testing.assert_allclose(segments[index],
                [[row["ci_low"], index], [row["ci_high"], index]],
                rtol=1e-9, atol=1e-12)
    wanted_colors = [colors.to_rgba("#C43C39" if pd.notna(value) and value < alpha
                                  else "#606060") for value in expected[gate]]
    np.testing.assert_array_equal(points.get_facecolors(), wanted_colors)
    np.testing.assert_array_equal(ax.get_yticks(), y)
    assert ax.get_xlabel() == "Model coefficient"
    np.testing.assert_array_equal(ax.lines[0].get_xdata(), [0, 0])


def observe(row):
    """Return original tables paired with every actual scientific drawing mark."""
    import matplotlib.pyplot as plt
    import pandas as pd
    from PyFLASH import report
    table = native_table(row)
    original = table.copy(deep=True)
    report.start()
    result = None
    try:
        result = draw(table, emit_report=True)
        records = report.collect()
        assert_native_report(records, original)
        fig = result["figure"]
        selected = table[table.term != "Intercept"]
        assert_native_marks(fig, selected)
        pd.testing.assert_frame_equal(result["coefficients"], original)
        pd.testing.assert_frame_equal(table, original)
        ax, = fig.axes
        expected_labels = [f"{item.dependent_variable}: {item.term}"
                           for item in selected.iloc[::-1].itertuples(index=False)]
        actual_labels = [tick.get_text() for tick in ax.get_yticklabels()]
        assert actual_labels == expected_labels
        assert ax.get_title() == "Linear model coefficients (p value, alpha=0.05)"
        assert result["path"] is None
        return {
            "native_table": table.to_dict("records"),
            "native_plotted_rows": selected.iloc[::-1].to_dict("records"),
            "actual_points": ax.collections[-1].get_offsets().tolist(),
            "actual_interval_segments": [segment.tolist() for segment in ax.collections[0].get_segments()],
            "actual_point_rgba": ax.collections[-1].get_facecolors().tolist(),
            "actual_row_positions": ax.get_yticks().tolist(),
            "actual_row_labels": actual_labels,
            "expected_row_labels": expected_labels,
            "actual_axis_label": ax.get_xlabel(),
            "actual_title": ax.get_title(),
            "actual_zero_line": list(ax.lines[0].get_xdata()),
            "actual_report_records": records,
        }
    finally:
        report.collect()
        if result is not None:
            plt.close(result["figure"])


def validate(output):
    import traceback
    from PyFLASH._persistence import write_json
    from reproducibility.normality_association_validation import comparison
    from reproducibility.run import json_clean
    fixture = check_identity()
    rows = []
    pairs = []
    for row in cases():
        error = None
        observed = None
        try:
            observed = observe(row)
        except Exception:
            error = traceback.format_exc()
        key = PREFIX + row["case"]["key"]
        agrees = error is None
        rows.append(comparison(key,
            "authenticated-original-native-R-linear-tables-and-corrections",
            "functional-precomputed-coefficient-drawing/no-additional-estimator-vote",
            {"all_native_marks_match": agrees}, {"all_native_marks_match": True},
            agrees, True, "native-estimates-and-CI-relative-1e-9/absolute-1e-12; exact-identities-and-color-decisions", 1e-9, 1e-12))
        pairs.append({"case": row["case"], "original_native_answers": row["expected"],
                      "observed": observed, "error": error, "agrees": agrees})
    control_pairs = []
    for name in uncertainty_cases():
        error = None
        observed = None
        try:
            observed = observe_uncertainty(name)
        except Exception:
            error = traceback.format_exc()
        agrees = error is None
        rows.append(comparison(PREFIX + 'supplied-uncertainty.' + name,
            'literal-supplied-boundaries/original-authenticated-native-estimate-and-probability',
            'functional-display-and-report-transport/no-additional-estimator-vote',
            {'supplied_values_preserved': agrees}, {'supplied_values_preserved': True},
            agrees, True, 'exact-input-endpoints-and-missingness', 0., 0.))
        control_pairs.append({'control': name, 'observed': observed, 'error': error, 'agrees': agrees})
    probability_pairs = []
    for index, (gate, column) in enumerate(probability_cases()):
        error = None
        observed = None
        try:
            observed = observe_probability(gate, column)
        except Exception:
            error = traceback.format_exc()
        agrees = error is None
        rows.append(comparison(PREFIX + 'probability-selector.' + str(index),
            'literal-selector-and-authenticated-native-probability-columns',
            'functional-color-title-report-and-refusal/no-additional-estimator-vote',
            {'named_probability_preserved': agrees}, {'named_probability_preserved': True},
            agrees, True, 'exact-column-selection-and-color-decisions', 0., 0.))
        probability_pairs.append({'selector': gate, 'column': column, 'observed': observed,
                                  'error': error, 'agrees': agrees})
    write_json(Path(output) / "linear-forest-native-paired.json", json_clean({
        "schema_version": 1,
        "complete_contract": False,
        "rows": pairs,
        "uncertainty_controls": control_pairs,
        "probability_controls": probability_pairs,
        "native_fixture": str(native.FIXTURE),
        "source_manifest": fixture["source_manifest"],
        "settings": {"save": False, "return_data": True, "emit_report": True,
                     "alpha": .05, "gate": "p", "title": "auto", "max_terms": 60},
        "scope": __doc__,
    }))
    return rows
