"""Invalid probabilities and changed random streams cannot masquerade as valid."""
from copy import deepcopy
import pytest
from reproducibility import presentation_cache_contract as contract

@pytest.mark.parametrize('case',contract.cases(),ids=lambda row:row['key'])
def test_full_functional_contract(case):
    original=deepcopy(case)
    assert contract.production(case)==case['expected']
    assert original==case

def test_before_correction_failures_remain_recorded():
    contract.check_identity()
    rows=contract.cases()
    assert len(rows)==509
    assert sum(row['original_failure'] for row in rows)==81

def test_partial_functional_evidence_cannot_certify_complete_contract():
    from reproducibility.run import inventory
    cases=contract.cases();keys={case['key'] for case in cases}
    capabilities={'PyFLASH.stats.get_annotation','PyFLASH.stats.stats_cache_key','PyFLASH.stats.clear_stats_cache'}
    complete={row['capability']:row for row in inventory(keys) if row['capability'] in capabilities}
    assert all(row['status']=='validated-complete-contract' for row in complete.values())
    assert all(row['kind'].startswith('functional-') for row in complete.values())
    for capability,row in complete.items():
        missing=row['executed_subcontracts'].split(';')[0]
        incomplete=next(r for r in inventory(keys-{missing}) if r['capability']==capability)
        assert incomplete['status']!='validated-complete-contract'

@pytest.mark.parametrize('legacy',[False,True])
def test_parent_recomputes_intervals_after_the_configured_stream_advances(monkeypatch,legacy):
    import pickle
    import numpy as np
    from types import SimpleNamespace
    from PyFLASH import stats
    from PyFLASH.config import Config
    monkeypatch.setattr(Config,'STATS_CACHE',True)
    monkeypatch.setattr(Config,'EFFECT_SIZES',True)
    monkeypatch.setattr(Config,'EFFECT_CI',True)
    monkeypatch.setattr(Config,'EFFECT_CI_RESAMPLES',400)
    monkeypatch.setattr(Config,'CORRECTION_AUDIT',False)
    stream=np.random.RandomState(17) if legacy else np.random.default_rng(17)
    monkeypatch.setattr(Config,'EFFECT_CI_RANDOM_STATE',stream)
    experiment=SimpleNamespace(condition_list=['A','B'])
    groups=[[1.,2.,3.,5.,8.,13.],[2.,3.,4.,7.,11.,19.]]
    def compute(key):
        return stats.multipleComparisons(experiment,groups,None,None,None,None,draw=False,
            group_labels=['A','B'],comparisons=['1-2'],stats_test='welch_t',cache_key=key)[3]
    stats.clear_stats_cache()
    try:
        compute('same-visible-key')
        stream.random(7)
        before=pickle.dumps(stream,protocol=5)
        cached=compute('same-visible-key')
        after=pickle.dumps(stream,protocol=5)
        assert after!=before
        monkeypatch.setattr(Config,'EFFECT_CI_RANDOM_STATE',pickle.loads(before))
        fresh=compute(None)
        assert fresh==cached
        assert pickle.dumps(Config.EFFECT_CI_RANDOM_STATE,protocol=5)==after
    finally:stats.clear_stats_cache()
