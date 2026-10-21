"""The full power contract also agrees with independent high-precision mathematics."""
import hashlib
import json
from pathlib import Path
import numpy as np
import pytest
from reproducibility import native_power, power_integral
from reproducibility.cases import RTOL, ATOL

REFERENCE = json.loads(power_integral.FIXTURE.read_text(encoding='utf-8'))


@pytest.mark.parametrize('row', REFERENCE['rows'], ids=lambda row: row['key'])
def test_independent_integral_power_contract(row):
    expected = [np.nan if value is None else value for value in row['expected']]
    np.testing.assert_allclose(native_power.production(row), expected,
                               rtol=RTOL, atol=ATOL, equal_nan=True)


def test_integral_contract_preserves_inputs_and_reference_code():
    assert [{key: row[key] for key in ('key','capability','parameters')}
            for row in REFERENCE['rows']] == native_power.cases()
    assert REFERENCE['reference_code_sha256'] == hashlib.sha256(
        Path(power_integral.__file__).read_bytes()).hexdigest()
