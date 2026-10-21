"""A complete declaration cannot turn absent or duplicated evidence into a pass."""
import pytest
from reproducibility import excel_whole_export_contract as contract


def test_every_frozen_case_is_assigned_to_a_whole_export_obligation():
    d = contract.declaration()
    expected = {key for family in d['families'] for key in family['keys']}
    assigned = {key for keys in d['required'].values() for key in keys}
    assert expected == assigned
    assert len(expected) == d['total_family_cases']
    assert set(d['required']) == contract.COMPLETE_CAPABILITIES


@pytest.mark.parametrize('defect', ['missing', 'duplicate', 'disagree', 'missingness', 'extra'])
def test_incomplete_or_invalid_evidence_cannot_qualify(monkeypatch, defect):
    monkeypatch.setattr(contract, 'declaration', lambda: dict(
        families=[dict(keys=['check.a', 'check.b'])], prefixes={'method': ['check.']},
        required={'method': ['check.a', 'check.b']}))
    good = lambda key: dict(contract=key, status='agree', frozen_reference_agrees=True, missingness_equal=True)
    rows = [good('check.a'), good('check.b')]
    assert contract.coverage(rows)['passed']
    if defect == 'missing': rows.pop()
    elif defect == 'duplicate': rows.append(good('check.a'))
    elif defect == 'disagree': rows[-1]['status'] = 'disagree'
    elif defect == 'missingness': rows[-1]['missingness_equal'] = False
    else: rows.append(good('check.unexpected'))
    assert not contract.coverage(rows)['passed']
