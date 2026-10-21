"""Full interval options and explicit invalid-request failures."""
import numpy as np
import pytest
from reproducibility import bootstrap_options_contract as reference
from PyFLASH.stats_extra import effect_ci

@pytest.mark.parametrize('case',reference.cases(),ids=lambda row:row['key'])
def test_complete_bootstrap_options_against_frozen_independent_endpoints(case):
    expected=reference.expected(case)
    assert reference.equal(reference.independently_recalculate(case),expected)
    assert reference.equal(reference.production(case),expected)

def test_frozen_bootstrap_options_identity():
    fixture=reference.check_identity()
    assert len(fixture['rows'])==518
    assert not fixture['original_failures']

INVALID=[{'eftype':v} for v in ['unknown','',None,True,[]]]
INVALID += [{'n_resamples':v} for v in [0,-1,1.5,'20',True,None]]
INVALID += [{'confidence':v} for v in [-.1,1.1,float('nan'),float('inf'),'0.95',True,None]]
INVALID += [{'random_state':v} for v in [-1,2**32,1.5,'17',True,object()]]

@pytest.mark.parametrize('options',INVALID)
@pytest.mark.parametrize('a,b',[([1,2,3],[2,4,5]),([],[])])
def test_invalid_options_are_errors_even_when_groups_are_too_small(options,a,b):
    with pytest.raises(ValueError):effect_ci(a,b,**options)

@pytest.mark.parametrize('a,b',[(1,[1,2,3]),([[1,2],[3,4]],[1,2,3]),([1,2,3],[[2,3],[4,5]])])
def test_groups_must_be_one_dimensional(a,b):
    with pytest.raises(ValueError):effect_ci(a,b,n_resamples=20)

def test_invalid_request_cannot_consume_supplied_random_generator():
    generator=np.random.default_rng(17);before=generator.bit_generator.state
    with pytest.raises(ValueError):effect_ci([1,2,3],[2,4,5],eftype='unknown',random_state=generator)
    assert generator.bit_generator.state==before


@pytest.mark.parametrize('failure',[MemoryError,RuntimeError])
def test_execution_failures_cannot_masquerade_as_undefined_intervals(monkeypatch,failure):
    from PyFLASH import stats_extra
    def failed(*args,**kwargs):raise failure('bootstrap could not execute')
    monkeypatch.setattr(stats_extra._sps,'bootstrap',failed)
    with pytest.raises(failure,match='could not execute'):
        effect_ci([1,2,3],[2,4,5],n_resamples=20)
