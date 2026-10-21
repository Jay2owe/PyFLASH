"""Whole rank inference, every report field, request preflight and discrete ties."""
from copy import deepcopy
import pytest
from reproducibility import rank_contract as contract

@pytest.mark.parametrize('case',contract.cases(),ids=lambda row:row['key'])
def test_complete_rank_report_matches_frozen_independent_answer(case):
    retained=deepcopy(case)
    assert contract.equal(contract.production(case),case['expected'])
    assert case==retained

def test_original_failures_and_all_answers_are_retained():
    fixture=contract.check_identity()
    assert len(fixture['rows'])==1220
    assert sum(row['original_failure'] for row in fixture['rows'])==1123

def test_invalid_rank_requests_precede_inference_and_report_mutation(monkeypatch):
    from PyFLASH import stats
    def forbidden(*args,**kwargs):raise AssertionError('Inference preceded validation')
    monkeypatch.setattr(stats,'_rank_design',forbidden)
    for groups in ([[1,2,3],[2,4,6]],[[],[]],[[2,2],[2,2]]):
        for method in ('Conover','Dunn','Nemenyi','DSCF'):
            for option in ({'comparisons':['0-2']},{'comparisons':['1-2'],'posthoc_correction':'made-up'}):
                raw={'caller':'preserved'}
                with pytest.raises(ValueError):stats.runKW(groups,results_dict=raw,posthoc=method,**option)
                assert raw=={'caller':'preserved'}

def test_discrete_rank_ties_count_the_observed_boundary():
    from PyFLASH import stats
    probabilities,*_=stats.runKW([[1,2],[3,4],[5,6]],['1-3','1-2'],{},posthoc='Conover',posthoc_correction='Westfall-Young')
    assert probabilities==[4/90,10/90]

def test_corrected_rank_strength_cache_is_bounded():
    from PyFLASH import stats
    assert stats._exact_rank_null_strengths.cache_info().maxsize==4

def test_whole_rank_parent_requires_every_report_and_external_witness():
    from reproducibility.run import inventory
    from reproducibility.rank_validation import required_keys
    keys=required_keys();capability='PyFLASH.stats.runKW'
    assert next(r for r in inventory(keys) if r['capability']==capability)['status']=='validated-complete-contract'
    for missing in ('rank-reports.complete.0','rank-range.ordinary.0.1','rank-native.ordinary.Conover'):
        assert next(r for r in inventory(keys-{missing}) if r['capability']==capability)['status']!='validated-complete-contract'

def test_changing_a_frozen_rank_answer_fails_identity(monkeypatch,tmp_path):
    import json
    payload=json.loads(contract.FIXTURE.read_text());payload['rows'][0]['expected']['method']='Changed'
    changed=tmp_path/'changed.json';changed.write_text(json.dumps(payload));monkeypatch.setattr(contract,'FIXTURE',changed)
    with pytest.raises(ValueError,match='differ from frozen'):contract.check_identity()
