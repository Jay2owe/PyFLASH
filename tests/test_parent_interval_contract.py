"""Protect all existing parent fields and every enabled confidence endpoint."""
from copy import deepcopy
import json
import pytest
from reproducibility import parent_interval_contract as contract

@pytest.mark.parametrize('case',contract.cases(),ids=lambda case:case['key'])
def test_complete_interval_enabled_parent_report(case):
    unchanged=deepcopy(case)
    assert contract.equal(contract.production(case),case['expected'])
    assert case==unchanged

def test_original_interval_reports_and_failed_capture_are_preserved():
    fixture=contract.check_identity()
    assert len(fixture['rows'])==4187
    assert not any(row['original_failure'] for row in fixture['rows'])
    assert sum(row['default_count'] for row in fixture['rows'])==7
    assert all(row['resamples']==5000 and row['seed']==17 for row in fixture['rows'] if row['default_count'])

def test_all_interval_reports_leave_other_parent_options_open():
    from reproducibility.run import inventory
    keys={row['key'] for row in contract.cases()}
    parent=next(row for row in inventory(keys) if row['capability']==contract.CAPABILITY)
    assert parent['status']=='partially-validated-contract'
    assert set(parent['executed_subcontracts'].split(';'))==keys

def test_changed_endpoint_is_refused(monkeypatch,tmp_path):
    fixture=json.loads(contract.FIXTURE.read_text(encoding='utf-8'))
    case,label=next((row,name) for row in fixture['rows']
        for name,value in row['expected'].get('results_dict',{}).items()
        if name.startswith('Effect ') and isinstance(value,list) and len(value)==2
        and isinstance(value[1],list) and len(value[1])==2)
    case['expected']['results_dict'][label][1][0]=123.
    changed=tmp_path/'changed.json';changed.write_text(json.dumps(fixture),encoding='utf-8')
    monkeypatch.setattr(contract,'FIXTURE',changed)
    with pytest.raises(ValueError,match='differ from original'):
        contract.check_identity()
