"""Public rhythm rows, raw-input preparation, identities and error schemas."""
import json, math
import numpy as np
import pandas as pd
import pytest
from PyFLASH.stats_extra import cosinor_table
from reproducibility import cosinor_table_contract as reference
from reproducibility.reference_runtime import values

def decoded(value):
    if isinstance(value,dict):
        if set(value)=={'nonfinite'}:return {'nan':math.nan,'positive_infinity':math.inf,'negative_infinity':-math.inf}[value['nonfinite']]
        return {k:decoded(v) for k,v in value.items()}
    if isinstance(value,list):return [decoded(v) for v in value]
    return value

@pytest.mark.parametrize('case',reference.cases(),ids=lambda r:r['key'])
def test_complete_public_table_against_frozen_independent_composition(case):
    fixture=json.loads(reference.FIXTURE.read_text(encoding='utf-8'))
    row=next(r for r in fixture['rows'] if r['case']['key']==case['key'])
    assert row['case']==case
    expected=decoded(row['expected']);actual=reference.production(case)
    assert reference.equal(actual,expected)
    for a,b in zip(actual['records'],expected['records'],strict=True):
        if b['p_rhythm']>0:np.testing.assert_allclose(a['p_rhythm'],b['p_rhythm'],rtol=1e-9,atol=0.)

def test_parent_reference_input_and_dependency_identity():
    fixture,queries=reference.check_identity()
    assert fixture['original_failures']
    for case,native in zip(reference.cases(),fixture['native']['rows'],strict=True):
        assert native['code']==reference.native_query(case)
        np.testing.assert_allclose(values(native),reference.preprocessing_answer(case),rtol=0,atol=0)
        expected=next(r['expected'] for r in fixture['rows'] if r['case']['key']==case['key'])
        assert reference.packed(reference.expected(case))==expected

@pytest.fixture
def observations():
    return pd.DataFrame({'t':[0.,4.,8.,12.,16.,20.]*2,
                         'y':[3.,4.,2.,1.,2.,4.,4.,4.,2.,2.,3.,5.],
                         'group':['A']*6+['B']*6,'animal':['Mouse 1']*6+['Mouse 2']*6})

@pytest.mark.parametrize('method',['pooled','population_mean','mixed'])
def test_original_rows_and_scratch_named_columns_are_not_mutated(observations,method):
    data=observations.rename(columns={'t':'_v','y':'_t','group':'_animal','animal':'_grp'})
    before=data.copy(deep=True)
    cosinor_table(data,'_v','_t',group_col='_animal',animal_col='_grp',method=method)
    pd.testing.assert_frame_equal(data,before)

@pytest.mark.parametrize('period',[0.,-1.,True,'24',None,float('nan'),float('inf')])
def test_period_domain_rejects_before_fitting(observations,period):
    with pytest.raises(ValueError,match='period'):
        cosinor_table(observations,'t','y',period=period)

@pytest.mark.parametrize('method',['unknown','',None,True])
def test_unknown_method_is_a_request_error(observations,method):
    with pytest.raises(ValueError,match='method'):
        cosinor_table(observations,'t','y',method=method)

@pytest.mark.parametrize('option',['time_col','value_col','group_col','animal_col'])
def test_requested_missing_column_is_not_silently_replaced(observations,option):
    options={'time_col':'t','value_col':'y','group_col':'group','animal_col':'animal','method':'population_mean'}
    options[option]='missing'
    with pytest.raises(ValueError,match='column'):
        cosinor_table(observations,**options)

@pytest.mark.parametrize('method',['population_mean','mixed'])
def test_repeated_measure_method_requires_subject_identity(observations,method):
    with pytest.raises(ValueError,match='animal_col'):
        cosinor_table(observations,'t','y',method=method)

@pytest.mark.parametrize('method',['population_mean','mixed'])
def test_repeated_measure_methods_reject_free_period_as_group_error(observations,method):
    table=cosinor_table(observations,'t','y',animal_col='animal',method=method,period_free=True)
    assert list(table.columns)==reference.FIELDS+(['n_subjects'] if method=='population_mean' else [])
    assert table.iloc[0]['method']==method
    assert 'fixed period' in table.iloc[0]['error'] and np.isnan(table.iloc[0]['p_rhythm'])

@pytest.mark.parametrize('value',[0,1,'yes',None])
def test_free_period_requires_boolean(observations,value):
    with pytest.raises(ValueError,match='period_free'):
        cosinor_table(observations,'t','y',period_free=value)

@pytest.mark.parametrize('column',['group','animal'])
def test_display_label_collision_cannot_merge_distinct_identities(observations,column):
    observations[column]=[1]*6+['1']*6
    if column=='animal':observations['group']='A'
    with pytest.raises(ValueError,match='identit'):
        cosinor_table(observations,'t','y',group_col='group',animal_col='animal',method='mixed')

def test_ambiguous_required_column_is_rejected(observations):
    data=pd.concat([observations,observations[['y']]],axis=1)
    with pytest.raises(ValueError,match='column'):
        cosinor_table(data,'t','y')

@pytest.mark.parametrize('method',['pooled','population_mean','mixed'])
def test_failed_group_keeps_output_schema_and_valid_group(observations,method):
    data=observations.iloc[:6].copy();data['group']='valid'
    if method!='pooled':
        second=data.copy();second['animal']='Mouse 2';second['y']+=1.
        data=pd.concat([data,second],ignore_index=True)
    sparse=pd.DataFrame({'t':[0.,6.],'y':[1.,2.],'group':['sparse']*2,'animal':['Mouse 1']*2})
    table=cosinor_table(pd.concat([data,sparse],ignore_index=True),'t','y',group_col='group',animal_col='animal',method=method)
    assert list(table.columns)==reference.FIELDS+(['n_subjects'] if method=='population_mean' else [])
    assert list(table['group'])==['valid','sparse'] and list(table['n'])==[len(data),2]
    assert table.iloc[0]['error'] is None
    assert table.iloc[1]['error'] and np.isnan(table.iloc[1]['p_rhythm'])
