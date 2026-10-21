"""Full normality fields, plot coordinates, retained failed rounds and gate scope."""
from copy import deepcopy
import json
import pytest
from reproducibility import normality_parent_contract as contract

@pytest.mark.parametrize('case',contract.cases(),ids=lambda row:row['key'])
def test_complete_normality_matches_frozen_independent_report(case):
    original=deepcopy(case)
    assert contract.equal(contract.production(case),case['expected'])
    assert case==original

def test_before_answers_and_original_failures_remain_preserved():
    fixture=contract.check_identity()
    assert len(fixture['rows'])==124
    assert sum(case['original_failure'] for case in fixture['rows'])==98

def test_native_zero_tail_diagnostics_supply_no_agreement_vote():
    from reproducibility.normality_parent_validation import native_cases,required_keys
    rows=native_cases();keys=required_keys()
    assert len(rows)==67
    assert sum(row['role']=='independent-native-corroboration' for row in rows)==49
    for row in rows:
        if row['role']=='retained-native-diagnostic':assert row['key'] not in keys

def test_parent_gate_needs_every_complete_report_and_native_corroboration():
    from reproducibility.normality_parent_validation import required_keys
    from reproducibility.run import inventory
    keys=required_keys();capability='PyFLASH.stats.test_normality'
    assert next(row for row in inventory(keys) if row['capability']==capability)['status']=='validated-complete-contract'
    assert next(row for row in inventory(keys-{'normality-parent.103'}) if row['capability']==capability)['status']!='validated-complete-contract'

def test_changed_normality_answer_fails_identity(monkeypatch,tmp_path):
    payload=json.loads(contract.FIXTURE.read_text(encoding='utf-8'));payload['rows'][0]['expected']['normal']=False
    altered=tmp_path/'altered.json';altered.write_text(json.dumps(payload))
    monkeypatch.setattr(contract,'FIXTURE',altered)
    with pytest.raises(ValueError,match='differ from frozen'):contract.check_identity()

def test_positive_subnormal_shapiro_probability_cannot_be_replaced_by_zero():
    case=next(row for row in contract.cases() if row['dataset']=='three-subnormal-positive-tail')
    expected=deepcopy(case['expected']);assert expected['results_dict']['SW_all'][1]>0
    changed=deepcopy(expected);changed['results_dict']['SW_all'][1]=0.
    assert not contract.equal(changed,expected)

def test_normality_weight_cache_uses_shared_memory_bound():
    from PyFLASH.stats import _normality_shapiro_weights
    _normality_shapiro_weights.cache_clear();_normality_shapiro_weights(5001)
    assert _normality_shapiro_weights.cache_bytes()<=64*1024**2
    assert _normality_shapiro_weights.cache_info().currsize==1
    _normality_shapiro_weights.cache_clear()
