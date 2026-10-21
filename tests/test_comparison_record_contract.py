"""Directions and all record fields follow measured values and declared group positions."""
from copy import deepcopy
import json
import pytest
from reproducibility import comparison_record_contract as contract


@pytest.mark.parametrize('case',contract.cases(),ids=lambda row:row['key'])
def test_complete_unaudited_record_matches_independent_schema(case):
    original=deepcopy(case)
    assert contract.equal(contract.production(case),case['expected'])
    assert case==original


def test_original_records_requests_answers_and_failures_remain_preserved():
    fixture=contract.check_identity()
    assert len(fixture['rows'])==576
    assert sum(row['original_failure'] for row in fixture['rows'])==270
    assert fixture['scientific_parent_complete'] is False


def test_unaudited_round_does_not_certify_unchecked_builder_options():
    from reproducibility.run import inventory
    keys={row['key'] for row in contract.cases()}
    row=next(row for row in inventory(keys) if row['capability']=='PyFLASH.report.build_comparison_record')
    assert row['status']=='partially-validated-contract'
    assert set(row['executed_subcontracts'].split(';'))==keys


def test_replacing_record_answer_fails_identity(monkeypatch,tmp_path):
    fixture=json.loads(contract.FIXTURE.read_text(encoding='utf-8'));fixture['rows'][0]['expected']['headline']='Erased evidence'
    path=tmp_path/'altered.json';path.write_text(json.dumps(fixture),encoding='utf-8');monkeypatch.setattr(contract,'FIXTURE',path)
    with pytest.raises(ValueError,match='differ from before-correction'):contract.check_identity()
