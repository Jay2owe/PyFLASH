"""Full slope estimates, uncertainty, labels, degrees and invalid/undefined cases."""
import copy
import numpy as np
import pandas as pd
import pytest
from PyFLASH.stats import interaction_slope_difference
from reproducibility import interaction_slope_contract as reference

@pytest.mark.parametrize('case',reference.cases(),ids=lambda row:row['key'])
def test_complete_slope_report_against_original_independent_answers(case):
    assert reference.equal(reference.production(case),reference.expected(case))

def test_slope_original_inputs_answers_first_failures_and_reference_identity():
    fixture=reference.check_identity()
    assert len(fixture['rows'])==948
    assert len(fixture['native_queries'])==816
    assert len(fixture['original_failures'])==330

def test_slope_inputs_and_positionally_aligned_covariates_are_preserved():
    case=next(row for row in reference.cases() if row['dataset']=='numeric-adjustment')
    p=copy.deepcopy(case['parameters'])
    cov=pd.DataFrame(p['covariates'],index=range(200,212))
    original=cov.copy(deep=True)
    p['covariates']=cov
    x,y=copy.deepcopy((p['x'],p['y']))
    result=interaction_slope_difference(**p)
    assert reference.equal(reference.clean(result),reference.expected(case))
    pd.testing.assert_frame_equal(cov,original)
    assert (p['x'],p['y'])==(x,y)

def test_duplicate_covariate_identities_fail_before_fitting(monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('Invalid columns reached fitting')
    monkeypatch.setattr(np.linalg,'lstsq',forbidden)
    cov=pd.DataFrame(np.ones((6,2)),columns=['age','age'])
    with pytest.raises(ValueError,match='unique'):
        interaction_slope_difference([1,2,3,1,2,3],[1,2,4,2,4,6],['a']*3+['b']*3,covariates=cov)

def test_hashable_tuple_group_identities_remain_valid():
    labels=[('a',1)]*3+[('b',2)]*3
    out=interaction_slope_difference([1,2,3,1,2,3],[1,2,4,2,4,6],labels,reference=('a',1))
    assert out['reference']==('a',1) and out['other']==('b',2)
    assert np.isfinite(out['p'])
