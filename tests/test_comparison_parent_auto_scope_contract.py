"""Automatic two-factor selection cannot depend on stale or empty plot arrays."""
from copy import deepcopy
import json
import pytest
from reproducibility import comparison_parent_auto_scope_contract as contract


@pytest.mark.parametrize('case',contract.cases(),ids=lambda row:row['key'])
def test_complete_auto_report_uses_fitted_observations(case):
    original=deepcopy(case)
    assert contract.equal(contract.production(case),case['expected'])
    assert case==original


def test_original_auto_requests_answers_and_failures_are_retained():
    fixture=contract.check_identity()
    assert len(fixture['rows'])==720
    assert sum(row['original_failure'] for row in fixture['rows'])==480
    assert fixture['scientific_parent_complete'] is False


def test_auto_scope_leaves_other_parent_options_open():
    from reproducibility.run import inventory
    keys={row['key'] for row in contract.cases()}
    row=next(row for row in inventory(keys) if row['capability']=='PyFLASH.stats.multipleComparisons')
    assert row['status']=='partially-validated-contract'
    assert set(row['executed_subcontracts'].split(';'))==keys


def test_replacing_auto_answer_fails_identity(monkeypatch,tmp_path):
    payload=json.loads(contract.FIXTURE.read_text(encoding='utf-8'))
    payload['rows'][0]['expected']['test']='Incorrect plot scope'
    altered=tmp_path/'altered.json';altered.write_text(json.dumps(payload),encoding='utf-8')
    monkeypatch.setattr(contract,'FIXTURE',altered)
    with pytest.raises(ValueError,match='differ from before-correction'):contract.check_identity()
