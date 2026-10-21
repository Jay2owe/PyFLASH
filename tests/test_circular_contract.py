"""Every circular output against answers frozen before the production fix."""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from reproducibility import circular_contract as contract
from reproducibility.reference_runtime import values

REFERENCE = json.loads(contract.FIXTURE.read_text(encoding='utf-8'))


@pytest.mark.parametrize('row', REFERENCE['rows'], ids=lambda row: row['key'])
@pytest.mark.parametrize('reference', ['native-R', 'astropy', 'mathematical'])
def test_every_reported_circular_field(row, reference):
    expected = values(row['references'][reference])
    actual = contract.production(row)
    np.testing.assert_allclose(contract.coordinates(actual, row['parameters']['period']),
                               contract.coordinates(expected, row['parameters']['period']),
                               rtol=1e-9, atol=1e-12, equal_nan=True)


def test_reference_adapter_inputs_and_native_kernel_remain_frozen():
    assert hashlib.sha256(Path(contract.__file__).read_bytes()).hexdigest() == REFERENCE['adapter_sha256']
    assert [{k: row[k] for k in ('key', 'capability', 'parameters')} for row in REFERENCE['rows']] == contract.cases()
    assert hashlib.sha256(contract.native_source().encode()).hexdigest() == REFERENCE['reference_kernel_sha256']


@pytest.mark.parametrize('method', ['circular_stats', 'rayleigh_test'])
@pytest.mark.parametrize('period', [0, -1, np.nan, np.inf, True, '24', None])
@pytest.mark.parametrize('data', [[], [1, 2]])
def test_invalid_period_rejected_even_without_observations(method, period, data):
    from PyFLASH import stats_extra
    with pytest.raises(ValueError, match='period'):
        getattr(stats_extra, method)(data, period=period)


@pytest.mark.parametrize('method', ['circular_stats', 'rayleigh_test'])
def test_missing_observations_are_omitted_without_mutating_the_input(method):
    from PyFLASH import stats_extra
    source = pd.Series([1, None, pd.NA, 2, np.inf, 3], dtype=object)
    before = source.copy(deep=True)
    answer = getattr(stats_extra, method)(source)
    assert answer == getattr(stats_extra, method)([1, 2, 3])
    pd.testing.assert_series_equal(source, before)
