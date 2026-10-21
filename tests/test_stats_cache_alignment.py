"""Cache identity must follow order, nested settings, styles and measurements."""
from copy import deepcopy
import pytest
from PyFLASH import stats
from PyFLASH.aesthetics import pyflash_style_context

def test_stats_cache_key_preserves_group_order():
    assert stats.stats_cache_key('Signal',['C','D'],[])!=stats.stats_cache_key('Signal',['D','C'],[])

def test_stats_cache_key_accepts_complete_nested_options_without_mutation():
    options={'covariates':['Age','Sex'],'cov_kwds':{'groups':[1,1,2,2]},'equal_var':False}
    original=deepcopy(options)
    key=stats.stats_cache_key('Signal',['C','D'],['Female'],options)
    hash(key)
    assert key==stats.stats_cache_key('Signal',['C','D'],['Female'],dict(reversed(list(options.items()))))
    changed=deepcopy(options);changed['covariates'].reverse()
    assert key!=stats.stats_cache_key('Signal',['C','D'],['Female'],changed)
    assert options==original

def test_stats_cache_key_tracks_the_active_annotation_thresholds():
    first=stats.stats_cache_key('Signal',['C','D'],[])
    with pyflash_style_context(significance_thresholds={.01:'evidence'},significance_ns='uncertain'):
        second=stats.stats_cache_key('Signal',['C','D'],[])
    assert first!=second

def test_same_caller_cache_key_cannot_reuse_changed_measurements(monkeypatch):
    from types import SimpleNamespace
    from PyFLASH.config import Config
    from PyFLASH import report
    monkeypatch.setattr(Config,'STATS_CACHE',True)
    monkeypatch.setattr(Config,'EFFECT_SIZES',False)
    monkeypatch.setattr(Config,'CORRECTION_AUDIT',False)
    experiment=SimpleNamespace(condition_list=['A','B'])
    def compute(groups,key):
        report.start()
        try:
            stats.multipleComparisons(experiment,groups,None,None,None,None,
                draw=False,group_labels=['A','B'],comparisons=['1-2'],
                stats_test='welch_t',cache_key=key)
            return report.collect()[0]
        finally:report.collect()
    stats.clear_stats_cache()
    try:
        original=compute([[1.,2.,3.,4.],[4.,5.,6.,7.]],'shared')
        changed=compute([[1.,2.,3.,4.],[8.,9.,10.,11.]],'shared')
        uncached=compute([[1.,2.,3.,4.],[8.,9.,10.,11.]],None)
        assert changed['test']==uncached['test']
        assert changed['pairwise']==uncached['pairwise']
        assert changed['test']!=original['test']
    finally:stats.clear_stats_cache()


@pytest.mark.parametrize('mutate_cached_hit', [False, True])
def test_returned_statistics_cannot_modify_later_cached_answers(monkeypatch, mutate_cached_hit):
    from types import SimpleNamespace
    from PyFLASH.config import Config
    monkeypatch.setattr(Config, 'STATS_CACHE', True)
    monkeypatch.setattr(Config, 'EFFECT_SIZES', False)
    monkeypatch.setattr(Config, 'CORRECTION_AUDIT', False)
    experiment = SimpleNamespace(condition_list=['A', 'B'])
    groups = [[1., 2., 3., 4.], [4., 5., 6., 7.]]
    def compute():
        return stats.multipleComparisons(
            experiment, groups, None, None, None, None, draw=False,
            group_labels=['A', 'B'], comparisons=['1-2'],
            stats_test='welch_t', cache_key='ownership')[3]
    stats.clear_stats_cache()
    try:
        answer = compute()
        expected = deepcopy(answer)
        if mutate_cached_hit:
            answer = compute()
        # Returned dictionaries are user-owned, including their nested fields.
        answer['caller_note'] = {'changed': True}
        for value in answer.values():
            if isinstance(value, dict):
                value['caller_changed_nested_field'] = True
        assert compute() == expected
    finally:
        stats.clear_stats_cache()
