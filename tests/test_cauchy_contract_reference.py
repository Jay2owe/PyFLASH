"""Extreme combinations retain the published estimator and precise tails."""
import json
import numpy as np
import pytest
from reproducibility import cauchy_contract as contract
from reproducibility.cases import RTOL, ATOL

ROWS = json.loads(contract.FIXTURE.read_text(encoding='utf-8'))['rows']


@pytest.mark.parametrize('row', ROWS, ids=lambda r:r['key'])
def test_cauchy_complete_reference(row):
    reference = contract.reference(row)
    from reproducibility.decimal_cauchy import reference as decimal_reference
    np.testing.assert_allclose(decimal_reference(row), reference, rtol=RTOL, atol=ATOL, equal_nan=True)
    frozen = [np.nan if v is None else v for v in row['expected']]
    np.testing.assert_allclose(reference, frozen, rtol=RTOL, atol=ATOL, equal_nan=True)
    np.testing.assert_allclose(contract.production(row), reference, rtol=RTOL, atol=ATOL, equal_nan=True)


def test_contract_freeze_covers_every_declared_case():
    assert [{key:r[key] for key in ('key', 'capability', 'parameters')} for r in ROWS] == contract.cases()
