"""Regression draft: literal grouping truth, not production-generated answers."""
from itertools import product
from copy import deepcopy
import pandas as pd
import pytest
from PyFLASH.dataframe import coerce_dataframe_input, from_dataframe
from PyFLASH.conditions import condition, conditionList, multiCondition, zipConditionLists

@pytest.mark.parametrize('explicit,dictionary,expected', [
    ({},{'condition_col':'Treatment','animal_col':'Subject','name':'Supplied'},
     ('Supplied',['C','D'],['C','D','C'],['s1','s2','s3'])),
    ({'condition_col':'Condition','animal_col':'AnimalName','name':'DataFrame'},
     {'condition_col':'Treatment','animal_col':'Subject','name':'Supplied'},
     ('DataFrame',['A','B'],['A','B','A'],['a1','a2','a3'])),
    ({'condition_col':'Treatment','animal_col':'Subject','name':'Chosen'},
     {'condition_col':'Condition','animal_col':'AnimalName','name':'Dictionary'},
     ('Chosen',['C','D'],['C','D','C'],['s1','s2','s3'])),
    ({},{},('DataFrame',['A','B'],['A','B','A'],['a1','a2','a3'])),
])
def test_table_options_preserve_dictionary_until_explicitly_overridden(explicit,dictionary,expected):
    frame=pd.DataFrame({'AnimalName':['a1','a2','a3'],'Subject':['s1','s2','s3'],
        'Condition':['A','B','A'],'Treatment':['C','D','C'],'Value':[1.,2.,3.]})
    original=frame.copy(deep=True)
    options=deepcopy(dictionary)
    obj=coerce_dataframe_input(frame,dataframe_kwargs=options,**explicit)
    name,names,values,subjects=expected
    assert obj.name==name
    assert [group.name for group in obj.condition_list]==names
    assert obj.summary['Condition'].tolist()==values
    assert obj.summary['AnimalName'].tolist()==subjects
    pd.testing.assert_frame_equal(frame,original)
    assert options==dictionary

@pytest.mark.parametrize('count',[3,4])
def test_crossed_table_designs_keep_every_primitive_factor(count):
    levels=[['F','M'],['C','D'],['E','L'],['Y','O']][:count]
    factors=['Sex','Treatment','Time','Age'][:count]
    tuples=list(product(*levels))
    frame=pd.DataFrame(tuples,columns=factors)
    frame['AnimalName']=[f's{i}' for i in range(len(frame))]
    frame['Value']=[float(i) for i in range(len(frame))]
    original=frame.copy(deep=True)
    obj=from_dataframe(frame,factor_cols=factors)
    assert obj.factor==factors
    assert list(obj.factorDict)==factors
    assert [group.name for group in obj.condition_list]==[''.join(parts) for parts in tuples]
    assert obj.summary['Condition'].tolist()==[''.join(parts) for parts in tuples]
    for factor,values in zip(factors,levels):
        assert [group.name for group in obj.factorDict[factor]]==values
        assert obj.summary[factor].tolist()==frame[factor].tolist()
    assert obj.summary['AnimalName'].tolist()==frame['AnimalName'].tolist()
    assert obj.summary['Value'].tolist()==frame['Value'].tolist()
    pd.testing.assert_frame_equal(frame,original)

def test_nested_compound_preserves_authored_style_and_flattens_factors():
    sex=condition('Female','F','#112233','Sex')
    treatment=condition('Control','C','#223344','Treatment')
    time=condition('Early','E','#334455','Time',style='///')
    authored=multiCondition([sex,treatment],name='custom',label='Custom label',color='#abcdef',style='hollow')
    nested=multiCondition([authored,time])
    assert nested.name=='customE'
    assert nested.label=='Custom labelEarly'
    assert nested.color=='#abcdef'
    assert nested.style=='hollow'
    assert nested.conditionsList==[sex,treatment,time]
    assert nested.factor==['Sex','Treatment','Time']
    groups=conditionList([nested])
    assert list(groups.factorDict)==['Sex','Treatment','Time']
    assert groups.factorDict=={'Sex':[sex],'Treatment':[treatment],'Time':[time]}
