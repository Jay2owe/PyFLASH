"""Effects preserve measurement differences and scale within whole parent reports."""
from copy import deepcopy
import json
import pytest
from reproducibility import comparison_parent_effect_contract as contract


@pytest.mark.parametrize('case',contract.cases(),ids=lambda row:row['key'])
def test_complete_parent_report_includes_correct_point_effects(case):
    original=deepcopy(case)
    assert contract.equal(contract.production(case),case['expected'])
    assert case==original


def test_original_effect_requests_answers_and_failures_are_retained():
    fixture=contract.check_identity()
    assert len(fixture['rows'])==4180
    assert sum(row['original_failure'] for row in fixture['rows'])==124
    assert fixture['scientific_parent_complete'] is False


def test_positive_effect_cannot_be_accepted_as_zero():
    assert not contract.equal({'Effect 1-2 (hedges_g)':[0.,['nan','nan']]},
        {'Effect 1-2 (hedges_g)':[1e-200,['nan','nan']]})


def test_point_effects_leave_other_parent_options_open():
    from reproducibility.run import inventory
    keys={row['key'] for row in contract.cases()}
    row=next(row for row in inventory(keys) if row['capability']=='PyFLASH.stats.multipleComparisons')
    assert row['status']=='partially-validated-contract'
    assert set(row['executed_subcontracts'].split(';'))==keys


def test_replacing_effect_answer_fails_identity(monkeypatch,tmp_path):
    payload=json.loads(contract.FIXTURE.read_text(encoding='utf-8'))
    payload['rows'][0]['expected']['test']='Incorrect effect family'
    altered=tmp_path/'altered.json';altered.write_text(json.dumps(payload),encoding='utf-8')
    monkeypatch.setattr(contract,'FIXTURE',altered)
    with pytest.raises(ValueError,match='differ from before-correction'):contract.check_identity()
