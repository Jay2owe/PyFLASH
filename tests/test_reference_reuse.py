"""Expensive external quadrature can be reused only with matching evidence."""
import json
import pytest
from reproducibility import reference_reuse, power_integral, native_power


def test_complete_reference_reuse_has_per_case_identity(tmp_path, monkeypatch):
    def forbidden(*args):
        raise AssertionError('Unchanged reference computation must be reused.')
    monkeypatch.setattr(power_integral, 'reference', forbidden)
    rows = reference_reuse.integral_power_values(tmp_path)
    receipt = json.loads((tmp_path/'integral-reference-receipt.json').read_text())
    assert len(rows) == len(receipt['rows']) == len(native_power.cases())
    assert all(row['reused'] and row['reference_key'] and row['fixture_sha256'] for row in receipt['rows'])
    assert len({row['reference_key'] for row in receipt['rows']}) == len(rows)
    assert 'reuse' in receipt['execution']


@pytest.mark.parametrize('field', ['reference_code_sha256','versions','parameters'])
def test_changed_reference_identity_rejects_reuse(tmp_path,monkeypatch,field):
    evidence = json.loads(power_integral.FIXTURE.read_text())
    if field == 'parameters':
        evidence['rows'][0]['parameters']['alpha'] = .123
    elif field == 'versions':
        evidence['versions']['mpmath'] = '0.0.invalid'
    else:
        evidence[field] = 'changed'
    fixture = tmp_path/'changed.json'
    fixture.write_text(json.dumps(evidence))
    monkeypatch.setattr(power_integral,'FIXTURE',fixture)
    with pytest.raises(ValueError,match='changed'):
        reference_reuse.integral_power_values(tmp_path)
    assert not (tmp_path/'integral-reference-receipt.json').exists()
