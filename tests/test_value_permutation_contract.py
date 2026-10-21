"""Complete frozen value-null outputs and invalid-request boundaries."""
import hashlib,json,math
from pathlib import Path
import numpy as np
import pytest
from PyFLASH import stats_extra as se
from reproducibility import value_permutation_contract as reference
from reproducibility.reference_runtime import values

FROZEN=json.loads(reference.FIXTURE.read_text(encoding='utf-8'))

@pytest.mark.parametrize('row',FROZEN['rows'],ids=lambda row:row['key'])
def test_complete_value_null_and_all_metadata_against_both_frozen_references(row):
    expected=values(row['expected'])
    np.testing.assert_allclose(reference.production(row),expected,rtol=1e-9,atol=1e-12,equal_nan=True)
    np.testing.assert_allclose(reference.mathematical(row),expected,rtol=1e-9,atol=1e-12,equal_nan=True)
    native=next(r for r in FROZEN['native']['rows'] if r['key']==row['key'])
    np.testing.assert_allclose(values(native),expected,rtol=1e-9,atol=1e-12,equal_nan=True)

def test_reference_code_input_and_common_arrangement_identities():
    assert hashlib.sha256(Path(reference.__file__).read_text(encoding='utf-8').encode()).hexdigest()==FROZEN['reference_code_sha256']
    assert reference.cases()==[{key:row[key] for key in case} for case,row in zip(reference.cases(),FROZEN['rows'],strict=True)]
    for row in FROZEN['rows']:assert reference.arrangements(row['parameters'])==row['arrangements']

def test_complete_native_execution_keeps_queries_and_a_bounded_recorded_deadline(tmp_path,monkeypatch):
    calls=[]
    def execute(queries,output,*,name,timeout):
        calls.append((queries,output,name,timeout))
        return FROZEN['native']
    monkeypatch.setattr(reference,'execute_queries',execute)
    assert reference.execute(tmp_path)==FROZEN['native']
    queries,output,name,timeout=calls[0]
    assert timeout==900 and output==tmp_path
    assert queries==[{k:r[k] for k in ('key','code')} for r in FROZEN['native']['rows']]
    assert max(r['parameters']['n_resamples'] for r in FROZEN['rows'])==10000
    for previous in FROZEN['verification_adapter_history']:
        source=Path(reference.__file__).parent/previous['original_adapter']
        assert hashlib.sha256(source.read_text(encoding='utf-8').encode()).hexdigest()==previous['original_sha256']

@pytest.mark.parametrize('kwargs',[
    {'groups':[]},{'groups':[[1,2]]},{'groups':[[],[1,2]]},
    {'groups':[[1],[2]]},{'groups':[[[1,2]],[3,4]]},
    {'groups':[[1,math.nan],[2,3]]},{'groups':[[1,math.inf],[2,3]]},
    {'groups':None},{'groups':[[1,'bad'],[2,3]]},
    {'n_resamples':0},{'n_resamples':-1},{'n_resamples':2.5},{'n_resamples':True},
    {'seed':-1},{'seed':1.5},{'seed':True},{'statistic':'unknown'}])
def test_invalid_request_is_rejected_before_random_draws(kwargs,monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('random generation started')
    monkeypatch.setattr(np.random,'default_rng',forbidden)
    parameters={'groups':[[1,2],[3,4]],**kwargs}
    with pytest.raises(ValueError):se.value_permutation_null(**parameters)

def test_equal_means_and_zero_variance_are_not_maximal_significance():
    null=se.value_permutation_null([[4,4],[4,4]],n_resamples=7)
    assert np.isnan(null['p']).all()

def test_returned_results_have_no_shared_mutable_state():
    parameters={'groups':[[1,2],[3,4]],'n_resamples':7,'seed':0}
    first=se.value_permutation_null(**parameters)
    before=first['p'].copy()
    first['p'][:]=123;first['pairs'].append((8,9));first['mode']='edited'
    second=se.value_permutation_null(**parameters)
    np.testing.assert_array_equal(second['p'],before)
    assert second['pairs']==[(0,1)] and second['mode']=='sampled'
