"""Preserved pair order, all inference fields, and honest partial-parent scope."""
from copy import deepcopy
import json
import pytest
from reproducibility import comparison_parent_inference_contract as contract


@pytest.mark.parametrize('case',contract.cases(),ids=lambda row:row['key'])
def test_combined_inference_report_matches_independent_answer(case):
    original=deepcopy(case)
    assert contract.equal(contract.production(case),case['expected'])
    assert case==original


def test_before_requests_answers_and_failures_remain_preserved():
    fixture=contract.check_identity()
    assert len(fixture['rows'])==2018
    assert sum(row['original_failure'] for row in fixture['rows'])==1050
    assert fixture['scientific_parent_complete'] is False


def test_inference_round_does_not_certify_unchecked_parent_options():
    from reproducibility.run import inventory
    keys={row['key'] for row in contract.cases()}
    row=next(row for row in inventory(keys) if row['capability']=='PyFLASH.stats.multipleComparisons')
    assert row['status']=='partially-validated-contract'
    assert set(row['executed_subcontracts'].split(';'))==keys


def test_replacing_preserved_empty_request_fails_identity(monkeypatch,tmp_path):
    payload=json.loads(contract.FIXTURE.read_text(encoding='utf-8'))
    assert payload['rows'][0]['child']['parameters']['comparisons']==[]
    payload['rows'][0]['child']['parameters']['comparisons']=['1-2']
    altered=tmp_path/'altered.json';altered.write_text(json.dumps(payload))
    monkeypatch.setattr(contract,'FIXTURE',altered)
    with pytest.raises(ValueError,match='differ from before-correction'):contract.check_identity()
