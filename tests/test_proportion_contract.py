"""Every contingency-table field agrees with native R and exact mathematics."""
import json
from pathlib import Path
import numpy as np
import pytest
from reproducibility import proportion_contract as contract
from reproducibility.reference_runtime import values
from reproducibility.cases import RTOL, ATOL

REFERENCE = json.loads(contract.FIXTURE.read_text(encoding='utf-8'))


@pytest.mark.parametrize('row', REFERENCE['rows'], ids=lambda row:row['key'])
@pytest.mark.parametrize('reference', ['native-R','exact-count-mathematics'])
def test_all_proportion_result_fields(row, reference):
    if reference == 'native-R':
        expected = values(row)
    else:
        expected = values({'values':row['mathematical_values'], 'nonfinite':row['mathematical_nonfinite']})
    np.testing.assert_allclose(contract.production(row),expected,rtol=RTOL,atol=ATOL,equal_nan=True)


def test_frozen_inputs_queries_runtime_and_independent_counts():
    assert [{key:row[key] for key in ('key','capability','parameters')}
            for row in REFERENCE['rows']] == contract.cases()
    assert REFERENCE['webR'] == '0.6.0' and REFERENCE['wasm_sha256']
    for row in REFERENCE['rows']:
        assert row['code'] == contract.r_query(row)
        np.testing.assert_allclose(contract.mathematical(row), values(row),
                                   rtol=RTOL,atol=ATOL,equal_nan=True)
