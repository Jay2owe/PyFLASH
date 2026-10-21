"""Both public power results agree with frozen, independently executed R."""
import json
import numpy as np
import pytest
from reproducibility import native_power
from reproducibility.cases import RTOL, ATOL

REFERENCE = json.loads(native_power.FIXTURE.read_text(encoding='utf-8'))


@pytest.mark.parametrize('row', REFERENCE['rows'], ids=lambda row:row['key'])
def test_native_r_power_contract(row):
    expected = [np.nan if value is None else value for value in row['values']]
    np.testing.assert_allclose(native_power.production(row),expected,
                               rtol=RTOL,atol=ATOL,equal_nan=True)


def test_native_contract_identity_covers_all_cases_and_pins_runtime():
    assert [{k:row[k] for k in ('key','capability','parameters')} for row in REFERENCE['rows']] == native_power.cases()
    assert REFERENCE['webR'] == '0.6.0' and REFERENCE['wasm_sha256']
    assert all(row['code'] == native_power.r_query(original)
               for row,original in zip(REFERENCE['rows'],native_power.cases(),strict=True))
