"""Public probability choices must select their named native input column."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.colors as colors
import matplotlib.pyplot as plt
import pandas as pd
import pytest

from reproducibility import linear_forest_contract as reference


@pytest.fixture(scope='module', autouse=True)
def original_native_probability_identity():
    reference.check_identity()


@pytest.mark.parametrize('gate, column', reference.probability_cases())
def test_registered_probability_observation_retains_native_values_and_refusals(gate, column):
    observed = reference.observe_probability(gate, column)
    assert observed['selector'] == gate
    if column is None:
        assert observed['actual_report_records'] == []
        assert 'refused' in observed
    else:
        assert observed['selected_column'] == column
        assert observed['actual_report_records']


@pytest.mark.parametrize('gate, column', [
    ('p', 'p_value'), ('p_value', 'p_value'), (' P ', 'p_value'),
    ('q', 'q_value'), ('q_value', 'q_value'), ('fdr', 'q_value'),
    (' Q ', 'q_value'), (' q_value ', 'q_value'), (' FDR ', 'q_value'),
])
def test_probability_choice_selects_the_named_native_column_with_optional_spaces(gate, column):
    # The interval is an explicitly supplied zero-width display control. The
    # original independently fitted estimate, p and q remain untouched.
    table = reference.uncertainty_table('defined-zero-width')
    before = table.copy(deep=True)
    p, q = table.p_value.iloc[0], table.q_value.iloc[0]
    assert 0 <= p < q <= 1
    # A client-selected display cutoff separates the original p and q; this
    # selects no new fit and changes no native expected answer.
    alpha = float((p + q) / 2)
    result = reference.draw(table, gate=gate, alpha=alpha)
    try:
        ax, = result['figure'].axes
        expected_color = '#C43C39' if table[column].iloc[0] < alpha else '#606060'
        assert ax.collections[-1].get_facecolors().tolist() == [list(colors.to_rgba(expected_color))]
        assert ('q value' if column == 'q_value' else 'p value') in ax.get_title()
        pd.testing.assert_frame_equal(table, before)
        pd.testing.assert_frame_equal(result['coefficients'], before)
    finally:
        plt.close(result['figure'])


@pytest.mark.parametrize('gate', ['unrecognized', 'qq'])
def test_unrecognized_probability_choice_is_refused_instead_of_using_raw_probabilities(gate):
    table = reference.uncertainty_table('defined-zero-width')
    before = table.copy(deep=True)
    with pytest.raises(ValueError, match='gate'):
        reference.draw(table, gate=gate)
    pd.testing.assert_frame_equal(table, before)
