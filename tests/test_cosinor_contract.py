"""Independent full fixed/free rhythm outputs and identifiable input domains."""
import hashlib
import json
import math
import numpy as np
import pytest
from reproducibility import cosinor_contract as reference
from reproducibility.reference_runtime import values
from PyFLASH.stats_extra import fit_cosinor


@pytest.mark.parametrize('row',reference.cases(),ids=lambda r:r['key'])
def test_full_frozen_cosinor_output(row):
    fixture=json.loads(reference.FIXTURE.read_text())
    frozen=next(r for r in fixture['rows'] if r['key']==row['key'])
    assert row=={key:frozen[key] for key in row}
    p=row['parameters']; kw={k:v for k,v in p.items() if k not in ['t','y','prediction_t']}
    if row.get('omit_bounds'): kw.pop('free_bounds',None)
    if row.get('omit_period'): kw.pop('period',None)
    answer=fit_cosinor([np.nan if v is None else float(v) for v in p['t']],
                       [np.nan if v is None else float(v) for v in p['y']],**kw)
    assert set(answer)=={'model','period','mesor','amplitude','acrophase','coef_cos','coef_sin','params',
                        'r_squared','f_stat','p','p_rhythm','n','predict'}
    assert answer['model']==('cosinor_free' if p['period_free'] else 'cosinor')
    assert type(answer['n']) is int
    names=['mesor','amplitude','acrophase']+(['period'] if p['period_free'] else [])
    assert list(answer['params'])==names
    for name,parameter in answer['params'].items():
        assert set(parameter)=={'value','stderr'}
        assert parameter['value']==answer[name] or math.isnan(parameter['value']) and math.isnan(answer[name])
    prediction=answer['predict'](p['prediction_t'])
    assert prediction.shape==(len(p['prediction_t']),)
    np.testing.assert_allclose(reference.production(row),values(frozen['mathematical']),rtol=1e-9,atol=1e-12,equal_nan=True)


T=[0,4,8,12,16,20]
Y=[1,4,3,2,0,1]
INVALID=[
    {'t':[[0,1],[2,3]],'y':[[1,2],[3,4]]},
    {'t':[0,1,2,3],'y':[1,2,3,4,5]},
    {'t':0,'y':Y},
    {'t':T,'y':[[1],[2],[3],[4],[5],[6]]},
    *[{'t':T,'y':Y,'period':v} for v in [0,-1,math.inf,math.nan,'bad']],
    *[{'t':T,'y':Y,'period_free':v} for v in [1,'yes',None]],
    {'t':T,'y':Y,'free_bounds':[16,36]},
    *[{'t':T,'y':Y,'period_free':True,'free_bounds':v} for v in [[36,16],[0,36],[-1,36],
        [16,math.inf],[math.nan,36],[16],[16,24,36],[[16,36]],[25,36]]],
    {'t':[0,6,12,18],'y':[1,2,3,4],'period_free':True},
    {'t':[0,0,0,0],'y':[1,2,3,4]},
    {'t':[0,0,0,0,0],'y':[1,2,3,4,5],'period_free':True},
    {'t':T,'y':[2]*6,'period_free':True},
    {'t':T,'y':[math.nan]*6},
]


@pytest.mark.parametrize('kwargs',INVALID)
def test_invalid_or_unidentified_cosinor_input(kwargs):
    with pytest.raises(ValueError): fit_cosinor(**kwargs)


@pytest.mark.parametrize('free',[False,True])
def test_cosinor_units_and_time_translation(free):
    t=np.array([0,3,7,11,15,20,24,30,37,45,57,63],float)
    y=4+2*np.cos(2*np.pi*(t-5)/25)+np.array([.01,-.02,.03,-.04,.02,.03,.01,-.02,.05,-.04,.01,.03])
    baseline=fit_cosinor(t,y,period=24,period_free=free)
    units=fit_cosinor(t/24,y,period=1,period_free=free)
    shift=fit_cosinor(t+6,y,period=24,period_free=free)
    np.testing.assert_allclose([units['period']*24,units['acrophase']*24,units['mesor'],units['amplitude']],
        [baseline[k] for k in ['period','acrophase','mesor','amplitude']],rtol=1e-9,atol=1e-12)
    assert shift['acrophase']==pytest.approx((baseline['acrophase']+6)%baseline['period'],rel=1e-9,abs=1e-12)
    np.testing.assert_allclose(shift['predict'](t+6),baseline['predict'](t),rtol=1e-9,atol=1e-12)
    names=['acrophase','period'] if free else ['acrophase']
    np.testing.assert_allclose([units['params'][k]['stderr']*24 for k in names],
        [baseline['params'][k]['stderr'] for k in names],rtol=1e-9,atol=1e-12)


def test_cosinor_published_and_native_references_remain_frozen():
    fixture=json.loads(reference.FIXTURE.read_text())
    reference.check_sources()
    from pathlib import Path
    canonical=Path(reference.__file__).read_text(encoding='utf-8').encode('utf-8')
    assert hashlib.sha256(canonical).hexdigest()==fixture['reference_code_sha256']
    cases=reference.cases()
    assert [{k:row[k] for k in declared} for row,declared in
            zip(fixture['rows'],cases,strict=True)]==cases
    native={row['key']:row for row in fixture['native']['rows']}
    for row in fixture['rows']:
        if row['reference_kind']=='mathematical-only':
            assert row['key'] not in native
            continue
        assert native[row['key']]['status']=='executed'
        np.testing.assert_allclose(values(native[row['key']]),values(row['mathematical']),rtol=1e-9,atol=1e-12,equal_nan=True)
