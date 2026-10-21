"""Complete scalar correction domains and probability tails, including huge counts."""
from copy import deepcopy
import json
import pytest
from reproducibility import scalar_multiplicity_contract as contract

@pytest.mark.parametrize('case',contract.cases(),ids=lambda row:row['key'])
def test_whole_scalar_correction_matches_frozen_independent_answer(case):
    original=deepcopy(case)
    assert contract.equal(contract.production(case),case['expected'])
    assert case==original

def test_scalar_correction_original_failures_and_answers_are_retained():
    fixture=contract.check_identity()
    assert len(fixture['rows'])==202
    assert sum(row['original_failure'] for row in fixture['rows'])==78

def test_small_probability_with_unrepresentable_count_has_finite_answer():
    from PyFLASH import stats
    for method in ('bonferroni_correction','sidak_correction'):
        p=getattr(stats,method)(5e-324,2**1024)
        assert 0<p<1

def test_report_wrapper_preserves_undefined_probabilities():
    import math
    from PyFLASH import stats
    for method in ('bonferroni','sidak'):
        actual=stats._apply_kw_correction([math.nan,.05],method)
        assert math.isnan(actual[0])
        assert actual[1]==getattr(stats,method+'_correction')(.05,2)

def test_whole_scalar_parent_keeps_old_and_complete_domain_requirements():
    from reproducibility.run import inventory
    from reproducibility.scalar_contracts import cases as earlier_cases
    earlier={'scalar.'+r['key'] for r in earlier_cases()}
    keys={r['key'] for r in contract.cases()}|earlier
    for method in ('bonferroni_correction','sidak_correction'):
        capability='PyFLASH.stats.'+method
        assert next(r for r in inventory(keys) if r['capability']==capability)['status']=='validated-complete-contract'
        missing=next(r['key'] for r in contract.cases() if r['method']==method)
        assert next(r for r in inventory(keys-{missing}) if r['capability']==capability)['status']!='validated-complete-contract'

def test_modified_scalar_answer_fails_before_identity(monkeypatch,tmp_path):
    payload=json.loads(contract.FIXTURE.read_text());payload['rows'][0]['expected']=.123
    changed=tmp_path/'changed.json';changed.write_text(json.dumps(payload));monkeypatch.setattr(contract,'FIXTURE',changed)
    with pytest.raises(ValueError,match='differ from frozen'):contract.check_identity()
