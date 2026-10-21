"""Frozen independent formulas check every returned field and accepted option."""
import json
import numpy as np
import pytest
from reproducibility import helper_contracts as reference
from reproducibility.cases import ATOL, RTOL

FROZEN = json.loads(reference.FIXTURE.read_text(encoding='utf-8'))['rows']


@pytest.mark.parametrize('row', FROZEN, ids=lambda row: row['key'])
def test_complete_helper_against_independent_reference(row):
    expected = np.asarray([np.nan if value is None else value for value in row['expected']], float)
    actual = np.asarray(reference.production(row), float)
    independent = np.asarray(reference.reference(row), float)
    assert actual.shape == independent.shape == expected.shape
    np.testing.assert_allclose(independent, expected, rtol=RTOL, atol=ATOL, equal_nan=True)
    np.testing.assert_allclose(actual, expected, rtol=RTOL, atol=ATOL, equal_nan=True)


def test_fixture_identity_and_completeness_gate_require_all_cases():
    assert [{key: row[key] for key in ('key', 'capability', 'parameters')} for row in FROZEN] == reference.cases()
    from reproducibility.run import inventory
    executed = ['helper.' + row['key'] for row in FROZEN]
    capabilities = {row['capability'] for row in FROZEN}
    complete = {row['capability'] for row in inventory(executed) if row['status'] == 'validated-complete-contract'}
    assert capabilities <= complete
    incomplete = {row['capability']: row for row in inventory(executed[1:])}
    assert incomplete[FROZEN[0]['capability']]['status'] != 'validated-complete-contract'
    assert incomplete['mean_bars']['status'] != 'validated-complete-contract'
