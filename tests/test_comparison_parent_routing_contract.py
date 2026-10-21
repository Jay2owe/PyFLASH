"""Full routing fields, original group positions and positive tiny probabilities."""
from copy import deepcopy
import json
import pytest
from reproducibility import comparison_parent_routing_contract as contract


@pytest.mark.parametrize('case',contract.cases(),ids=lambda row:row['key'])
def test_full_routing_report_matches_frozen_independent_answer(case):
    original=deepcopy(case)
    assert contract.equal(contract.production(case),case['expected'])
    assert case==original


def test_all_before_answers_and_original_failed_reports_remain_preserved():
    fixture=contract.check_identity()
    assert len(fixture['rows'])==2162
    assert sum(row['original_failure'] for row in fixture['rows'])==467
    assert fixture['scientific_parent_complete'] is False


def test_routing_round_does_not_certify_unchecked_parent_options():
    from reproducibility.run import inventory
    keys={row['key'] for row in contract.cases()}
    row=next(row for row in inventory(keys) if row['capability']=='PyFLASH.stats.multipleComparisons')
    assert row['status']=='partially-validated-contract'
    assert set(row['executed_subcontracts'].split(';'))==keys


def test_positive_subnormal_ks_probability_cannot_be_replaced_by_zero():
    case=next(row for row in contract.cases() if row.get('high_precision_ks')
        and 0<row['expected']['results_dict']['KS'][1]<1e-310)
    actual=contract.production(case)
    assert contract.equal(actual,case['expected'])
    changed=deepcopy(actual);changed['results_dict']['KS'][1]=0.
    assert not contract.equal(changed,case['expected'])


def test_normality_gate_requires_every_new_upper_branch_witness():
    from reproducibility.normality_parent_validation import required_keys
    from reproducibility.run import inventory
    keys=required_keys()
    witnesses={row['key'] for row in contract.cases() if row.get('high_precision_ks')}
    assert len(witnesses)==270 and witnesses<=keys
    row=next(row for row in inventory(keys-witnesses) if row['capability']=='PyFLASH.stats.test_normality')
    assert row['status']!='validated-complete-contract'


def test_replacing_empty_middle_group_fails_identity(monkeypatch,tmp_path):
    payload=json.loads(contract.FIXTURE.read_text(encoding='utf-8'))
    case=next(row for row in payload['rows'] if row.get('dataset')=='missing-middle')
    case['groups'][1]=[5.,6.,7.]
    altered=tmp_path/'altered.json';altered.write_text(json.dumps(payload))
    monkeypatch.setattr(contract,'FIXTURE',altered)
    with pytest.raises(ValueError,match='differ from before-correction'):contract.check_identity()
