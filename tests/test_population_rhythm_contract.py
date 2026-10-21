"""Published and mathematical population branch answers, including public rows."""
import json,math
import numpy as np
import pandas as pd
import pytest
from PyFLASH.stats_extra import _population_mean_cosinor,cosinor_table
from reproducibility import population_rhythm_contract as reference
from reproducibility.reference_runtime import values

@pytest.mark.parametrize('row',reference.cases(),ids=lambda r:r['key'])
def test_complete_population_branch_against_independent_frozen_answers(row):
    fixture=json.loads(reference.FIXTURE.read_text(encoding='utf-8'));frozen=next(r for r in fixture['rows'] if r['key']==row['key'])
    assert row=={k:frozen[k] for k in row}
    actual=reference.production(row);expected=values(frozen['mathematical'])
    np.testing.assert_allclose(actual,expected,rtol=1e-9,atol=1e-12,equal_nan=True)
    if expected[5]>0:np.testing.assert_allclose(actual[5],expected[5],rtol=1e-9,atol=0.)
    data=pd.DataFrame(row['parameters']['records'],columns=['t','y','animal'])
    table=cosinor_table(data,'t','y',animal_col='animal',period=row['parameters']['period'],method='population_mean')
    assert len(table)==1 and table.iloc[0]['group']=='all'
    result=table.iloc[0]
    assert result['method']=='population_mean' and result['error'] is None
    assert result['n']==len(reference.finite_records(row))
    np.testing.assert_allclose([result[k] for k in reference.FIELDS],expected,rtol=1e-9,atol=1e-12,equal_nan=True)

def test_population_reference_and_published_source_remain_frozen():
    fixture,queries=reference.check_identity();native={r['key']:r for r in fixture['native']['rows']}
    assert len(fixture['rows'])==51 and len(queries)==52
    for row in fixture['rows']:
        expected=values(row['mathematical'])
        np.testing.assert_allclose(reference.mathematical(row),expected,rtol=1e-9,atol=1e-12,equal_nan=True)
        if row['key'] in fixture['native_diagnostics']:continue
        np.testing.assert_allclose(values(native[row['key']]),expected,rtol=1e-9,atol=1e-12,equal_nan=True)

def test_population_cannot_average_coefficients_fitted_at_different_periods():
    row=reference.cases()[0];data=pd.DataFrame(reference.finite_records(row),columns=['_t','_v','animal'])
    with pytest.raises(ValueError,match='shared fixed period'):
        _population_mean_cosinor(data,'animal',row['parameters']['period'],True)
