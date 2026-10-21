"""Independent complete harmonic-group outputs and rejected ambiguous inputs."""
import json,math
import numpy as np
import pandas as pd
import pytest
from PyFLASH.stats_extra import cosinor_group_test
from reproducibility import group_rhythm_contract as reference
from reproducibility.reference_runtime import values

@pytest.mark.parametrize('row',reference.cases(),ids=lambda r:r['key'])
def test_complete_group_rhythm_against_frozen_independent_answers(row):
    fixture=json.loads(reference.FIXTURE.read_text(encoding='utf-8'))
    frozen=next(r for r in fixture['rows'] if r['key']==row['key'])
    assert row=={k:frozen[k] for k in row}
    actual=reference.production(row);expected=values(frozen['mathematical'])
    np.testing.assert_allclose(actual,expected,rtol=1e-9,atol=1e-12,equal_nan=True)
    if math.isfinite(expected[1]) and expected[1]>0:
        # An absolute tolerance must not approve a false zero significance.
        np.testing.assert_allclose(actual[1],expected[1],rtol=1e-9,atol=0.)

def test_frozen_group_rhythm_reference_identity_and_native_equivalence():
    fixture,queries=reference.check_identity()
    native={r['key']:r for r in fixture['native']['rows']}
    assert len(queries)==57
    assert len(fixture['native_diagnostics'])==5
    assert sum('original_failure' in r for r in fixture['rows'])==10
    for row in fixture['rows']:
        expected=values(row['mathematical'])
        np.testing.assert_allclose(reference.mathematical(row),expected,rtol=1e-9,atol=1e-12,equal_nan=True)
        if row['key'] in fixture['native_diagnostics']:continue
        np.testing.assert_allclose(values(native[row['key']]),expected,rtol=1e-9,atol=1e-12,equal_nan=True)
        if math.isfinite(expected[1]) and expected[1]>0:
            np.testing.assert_allclose(values(native[row['key']])[1],expected[1],rtol=1e-9,atol=0.)

@pytest.mark.parametrize('period',[0,-1,np.nan,np.inf,-np.inf,True,False,'24',None,[24]])
def test_invalid_group_period_is_rejected_before_time_resolution(period,monkeypatch):
    import PyFLASH.stats_extra as module
    def unexpected(*args,**kwargs):raise AssertionError('Invalid period reached time preparation.')
    monkeypatch.setattr(module,'_resolve_numeric_time',unexpected)
    with pytest.raises(ValueError,match='period'):
        cosinor_group_test(pd.DataFrame(columns=['t','y','g']),'t','y','g',period=period)

def test_distinct_groups_cannot_merge_under_one_rendered_label():
    data=pd.DataFrame({'t':[0,4,8,12,16,20]*2,'y':[1,4,3,2,0,1]*2,'g':[1]*6+['1']*6})
    with pytest.raises(ValueError,match='group.*label'):
        cosinor_group_test(data,'t','y','g')

def test_group_test_does_not_change_the_supplied_table():
    row=reference.cases()[45];p=row['parameters'];data=pd.DataFrame(p['records'],columns=p['columns']);original=data.copy(deep=True)
    cosinor_group_test(data,p['time_col'],p['value_col'],p['group_col'],period=p['period'])
    pd.testing.assert_frame_equal(data,original)
