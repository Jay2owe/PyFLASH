"""Complete interior/boundary Gaussian mixed rhythm answers, including public rows."""
import json
import hashlib
from fractions import Fraction
import numpy as np
import pandas as pd
import pytest
from PyFLASH.stats_extra import cosinor_table,_mixed_cosinor
from reproducibility import mixed_rhythm_contract as reference
from reproducibility.reference_runtime import values

FROZEN=json.loads(reference.FIXTURE.read_text(encoding='utf-8'))

@pytest.mark.parametrize('row',reference.cases(),ids=lambda r:r['key'])
def test_complete_mixed_branch_against_independent_frozen_answers(row):
    frozen=next(r for r in FROZEN['rows'] if r['key']==row['key']);assert row=={k:frozen[k] for k in row}
    actual=reference.production(row);expected=values(frozen['mathematical'])
    np.testing.assert_allclose(actual,expected,rtol=1e-9,atol=1e-12,equal_nan=True)
    if expected[5]>0:np.testing.assert_allclose(actual[5],expected[5],rtol=1e-9,atol=0.)
    data=pd.DataFrame(row['parameters']['records'],columns=['t','y','animal'])
    table=cosinor_table(data,'t','y',animal_col='animal',period=row['parameters']['period'],method='mixed')
    assert len(table)==1
    result=table.iloc[0];assert result['group']=='all' and result['method']=='mixed' and result['error'] is None
    assert result['n']==len(reference.prepared(row))
    np.testing.assert_allclose([result[k] for k in reference.FIELDS],expected,rtol=1e-9,atol=1e-12,equal_nan=True)
    if expected[5]>0:np.testing.assert_allclose(result['p_rhythm'],expected[5],rtol=1e-9,atol=0.)

def test_mixed_reference_identity_native_equivalence_and_preserved_failures():
    fixture,queries=reference.check_identity();lookup={r['key']:r for r in fixture['native']['rows']}
    assert len(queries)==33 and sum(r.get('variance_boundary',False) for r in fixture['rows'])==6
    old_path=reference.FIXTURE.with_name('mixed_rhythm_reference.json')
    assert hashlib.sha256(old_path.read_bytes()).hexdigest()==fixture['previous_fixture_sha256']
    assert json.loads(old_path.read_text(encoding='utf-8'))['rows']==fixture['rows']
    assert sum('original_failure' in r for r in fixture['rows'])==30
    for row in fixture['rows']:
        expected=values(row['mathematical'])
        np.testing.assert_allclose(reference.mathematical(row),expected,rtol=1e-9,atol=1e-12,equal_nan=True)
        np.testing.assert_allclose(values(lookup[row['key']]),expected,rtol=1e-9,atol=1e-12,equal_nan=True)
        if expected[5]>0:np.testing.assert_allclose(values(lookup[row['key']])[5],expected[5],rtol=1e-9,atol=0.)
    published=fixture['published_optimizer_diagnostics']
    assert len(published['rows'])==24 and sum(r['agrees'] for r in published['rows'])==4
    assert published['package_identity'][0]['values']==['3.1.169']
    assert published['package_identity'][1]['values']==['nlme.so=e3b1373690639f255e239b41bc17f935']

@pytest.mark.parametrize('row',reference.zero_noise_cases(),ids=lambda r:r['key'])
def test_exact_zero_noise_has_no_finite_gaussian_variance_fit(row):
    records=row['parameters']['records']
    residuals=[Fraction(str(y))-(Fraction(2+2*int(a.rsplit(' ',1)[-1]))+Fraction(c)+Fraction(s,2)) for t,y,a,c,s in records]
    assert sum(v*v for v in residuals)==0
    native=next(r for r in FROZEN['native']['rows'] if r['key']==row['key'])
    assert native['code']==reference.zero_noise_native_query(row)
    assert np.all(np.diff(values(native))>0)
    frame=pd.DataFrame([r[:3] for r in records],columns=['_t','_v','animal'])
    with pytest.raises(ValueError,match='positive residual variance'):
        _mixed_cosinor(frame,'animal',24.)
    frame=frame.rename(columns={'_t':'t','_v':'y'})
    result=cosinor_table(frame,'t','y',animal_col='animal',method='mixed').iloc[0]
    assert 'positive residual variance' in result['error']
    assert np.isnan(result['p_rhythm'])
