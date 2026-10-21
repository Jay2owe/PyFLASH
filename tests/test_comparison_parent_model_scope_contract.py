"""Retained model rows govern prerequisite and fitted numbers together."""
from copy import deepcopy
import json
import pytest
from reproducibility import comparison_parent_model_scope_contract as contract


@pytest.mark.parametrize('case',contract.cases(),ids=lambda row:row['key'])
def test_model_parent_report_matches_independent_fitted_scope(case):
    original=deepcopy(case)
    assert contract.equal(contract.production(case),case['expected'])
    assert case==original


def test_original_plot_requests_fitted_answers_and_failures_remain_preserved():
    fixture=contract.check_identity()
    assert len(fixture['rows'])==1284
    assert sum(row['original_failure'] for row in fixture['rows'])==1024
    assert fixture['scientific_parent_complete'] is False


def test_model_scope_round_does_not_certify_unchecked_parent_options():
    from reproducibility.run import inventory
    keys={row['key'] for row in contract.cases()}
    row=next(row for row in inventory(keys) if row['capability']=='PyFLASH.stats.multipleComparisons')
    assert row['status']=='partially-validated-contract'
    assert set(row['executed_subcontracts'].split(';'))==keys


def test_replacing_fitted_scope_answer_fails_identity(monkeypatch,tmp_path):
    payload=json.loads(contract.FIXTURE.read_text(encoding='utf-8'))
    payload['rows'][0]['expected']['test']='Stale plot-array test'
    altered=tmp_path/'altered.json';altered.write_text(json.dumps(payload))
    monkeypatch.setattr(contract,'FIXTURE',altered)
    with pytest.raises(ValueError,match='differ from before-correction'):contract.check_identity()
