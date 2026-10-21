"""Verify public chart output and preserve independent original failures."""
from copy import deepcopy
import json
import pytest
from reproducibility import mean_bars_contract as contract

@pytest.mark.parametrize('case',contract.cases(),ids=lambda row:row['key'])
def test_public_chart_preserves_all_supplied_scientific_artists(case):
    original=deepcopy(case);answer=contract.reference.report(case)
    assert answer==case['expected']
    assert not contract.differences(answer,contract.production(case),case['request']['points'])
    assert case==original

def test_original_failures_and_tolerance_are_preserved():
    fixture=contract.check_identity()
    assert len(fixture['rows'])==32 and sum(row['original_failure'] for row in fixture['rows'])==6
    assert fixture['tolerance']=={'relative':1e-12,'absolute':0}

def test_checked_artists_leave_remaining_public_plot_options_open():
    from reproducibility.run import inventory
    keys={row['key'] for row in contract.cases()}
    owner=next(row for row in inventory(keys) if row['capability']==contract.CAPABILITY)
    assert owner['status']=='partially-validated-contract'
    assert set(owner['executed_subcontracts'].split(';'))==keys

def test_changed_uncertainty_answer_is_refused(tmp_path,monkeypatch):
    fixture=json.loads(contract.FIXTURE.read_text(encoding='utf-8'))
    fixture['rows'][0]['expected']['uncertainty'][0]['tip']=123.
    target=tmp_path/'changed.json';target.write_text(json.dumps(fixture),encoding='utf-8')
    monkeypatch.setattr(contract,'FIXTURE',target)
    with pytest.raises(ValueError,match='differ from original'):contract.check_identity()
