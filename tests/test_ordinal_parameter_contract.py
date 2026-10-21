"""Frozen complete parameter events and refusal of unknown names."""
from copy import deepcopy
import json
import pytest
from reproducibility import ordinal_parameter_contract as contract

@pytest.mark.parametrize('case',contract.cases(),ids=lambda case:case['key'])
def test_complete_parameter_event_sequence(case):
    unchanged=deepcopy(case)
    assert contract.production(case)==case['expected']
    assert case==unchanged

def test_original_failures_and_protocol_are_retained():
    fixture=contract.check_identity()
    assert len(fixture['rows'])==108
    assert sum(case['original_failure'] for case in fixture['rows'])==60

def test_missing_case_keeps_both_parameter_owners_incomplete():
    from reproducibility.run import inventory
    keys={case['key'] for case in contract.cases()}
    complete={row['capability']:row for row in inventory(keys)}
    incomplete={row['capability']:row for row in inventory(keys-{'ordinal-parameters.4'})}
    for owner in contract.CAPABILITIES:
        assert complete[owner]['status']=='validated-complete-contract'
        assert incomplete[owner]['status']!='validated-complete-contract'
    for name in ('fit','predict','predict_proba'):
        assert complete['PyFLASH.modelling._PyFLASHOrdinalLogistic.'+name]['status']!='validated-complete-contract'

def test_altered_protocol_answer_is_refused(monkeypatch,tmp_path):
    fixture=json.loads(contract.FIXTURE.read_text(encoding='utf-8'))
    fixture['rows'][0]['expected']['after']['alpha']=999
    altered=tmp_path/'altered.json';altered.write_text(json.dumps(fixture),encoding='utf-8')
    monkeypatch.setattr(contract,'FIXTURE',altered)
    with pytest.raises(ValueError,match='differ from original'):
        contract.check_identity()
