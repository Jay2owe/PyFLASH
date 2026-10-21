"""Finite observations retain tiny test statistics and positive small tails."""
from copy import deepcopy
import pytest
from reproducibility import extreme_inference_contract as contract

@pytest.mark.parametrize('case',contract.cases(),ids=lambda row:row['key'])
def test_complete_report_against_independent_before_answers(case):
    original=deepcopy(case)
    assert contract.equal(contract.production(case),case['expected'])
    assert case==original

def test_all_41_failing_reports_remain_archived():
    fixture=contract.check_identity()
    assert len(fixture['rows'])==65
    assert sum(r['original_failure'] for r in fixture['rows'])==41

def test_zero_cannot_match_a_tiny_statistic_or_probability():
    assert not contract.equal(0.,1e-300)
    assert not contract.equal({'t':0.},{'t':1e-300})

def test_extreme_fields_are_required_by_each_whole_parent():
    from reproducibility.run import inventory
    from reproducibility.one_way_validation import required_keys as ordinary_keys
    from reproducibility.welch_one_way_validation import required_keys as welch_keys
    families={'ordinary':ordinary_keys(),'welch':welch_keys()}
    for family,capability in [('ordinary','PyFLASH.stats.runOWA'),('welch','PyFLASH.stats.runWelchOWA')]:
        keys=families[family];extra=contract.required_keys(family)
        assert extra<=keys
        assert next(r for r in inventory(keys) if r['capability']==capability)['status']=='validated-complete-contract'
        assert next(r for r in inventory(keys-{next(iter(extra))}) if r['capability']==capability)['status']!='validated-complete-contract'
