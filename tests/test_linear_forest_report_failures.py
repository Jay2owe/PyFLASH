"""A refused plot must not contribute a success record to the next result."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import pytest

from PyFLASH import report
from PyFLASH.plotting import plot_linear_model_coefficient_forest
from reproducibility import linear_forest_contract as reference


@pytest.mark.parametrize('existing', [False, True])
@pytest.mark.parametrize('kind, message', [
    ('reversed-bounds', 'lower bounds must not exceed upper bounds'),
    ('intercept-only', 'No coefficient forest figure could be created'),
])
def test_refused_plot_does_not_leave_a_success_record_or_discard_prior_records(existing, kind, message):
    reference.check_identity()
    table = reference.uncertainty_table('reversed-bounds')
    if kind == 'intercept-only':
        table['term'] = 'Intercept'
    before = table.copy(deep=True)
    figure_numbers = plt.get_fignums()
    report.start()
    expected = [{'kind': 'earlier-result', 'value': 17}] if existing else []
    for record in expected:
        report.emit(record)
    try:
        with pytest.raises(ValueError, match=message):
            plot_linear_model_coefficient_forest(coefficients=table, save=False)
        assert report.collect() == expected
        assert plt.get_fignums() == figure_numbers
        pd.testing.assert_frame_equal(table, before)
    finally:
        report.collect()
