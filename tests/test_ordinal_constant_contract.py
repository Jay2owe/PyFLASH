"""Identical-row training laws with all original answers and ordinary fits preserved."""
from copy import deepcopy
import json
import pytest
from reproducibility import ordinal_constant_contract as contract

@pytest.mark.parametrize('row',contract.cases(),ids=lambda row:row['case']['key'])
def test_every_fit_and_held_out_response_matches_independent_optimum(row):
    before=deepcopy(row);answer=contract.reference.report(row['case'])
    assert contract.equal(answer,row['expected'])
    assert contract.equal(contract.production(row['case']),answer)
    assert row==before

def test_every_original_constant_feature_failure_is_preserved():
    fixture=contract.check_identity()
    assert len(fixture['rows'])==72
    assert all(row['original_failure'] for row in fixture['rows'])

def test_constant_rows_leave_general_fit_options_open():
    from reproducibility.run import inventory
    keys={row['case']['key'] for row in contract.cases()}
    owner=next(row for row in inventory(keys) if row['capability']=='PyFLASH.modelling._PyFLASHOrdinalLogistic.fit')
    assert owner['status']=='partially-validated-contract'

def test_altered_coefficient_is_rejected(tmp_path,monkeypatch):
    fixture=json.loads(contract.FIXTURE.read_text(encoding='utf-8'))
    fixture['rows'][0]['expected']['coef'][0]=.1
    path=tmp_path/'changed.json';path.write_text(json.dumps(fixture),encoding='utf-8')
    monkeypatch.setattr(contract,'FIXTURE',path)
    with pytest.raises(ValueError,match='differ from original'):contract.check_identity()
