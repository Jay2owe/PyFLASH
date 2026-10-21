"""Independent relational and literal contracts for iteration data access.

SQLite performs selection/aggregation; literal records describe metadata and
iteration order. No PyFLASH callable generates a reference answer.
"""
from types import SimpleNamespace
from fractions import Fraction
from copy import deepcopy
import sqlite3
import math
from numbers import Real, Integral
from pathlib import Path

FIXTURE = Path(__file__).parent/'fixtures/iteration_contract_reference.json'

COLUMNS = ['Condition','Sex','Dose','Value','Other','AnimalName']
DTYPES = ['object','object','float64','float64','float64','object']
INPUT = [
    ['male','male',0,1.,10.,'s3'],
    ['female','female',2,3.,30.,'s1'],
    ['male','male',0,5.,50.,'s3'],
    ['female','female',1,None,70.,'s1'],
    ['female','female',2,9.,None,'s2'],
    ['extra',None,None,-2.,20.,'s4'],
]
NOISY_INPUT = [
    ['male','male',0,1.1,10.3,'s3'],
    ['female','female',2,3.3,30.7,'s1'],
    ['male','male',0,5.7,50.1,'s3'],
    ['female','female',1,None,70.9,'s1'],
    ['female','female',2,9.25,None,'s2'],
    ['extra',None,None,-2.2,20.6,None],
]
MARKER_COLUMNS = ['AnimalName','Region','Object','Condition','Value']
MARKERS = [
    ['s3','r3',0,'male',1.],['s3','r3',1,'male',5.],
    ['s1','r1',0,'female',3.],['s1','r2',0,'female',7.],
    ['s2','r1',0,'female',9.],['s4','r9',0,'extra',-2.],
]
REGIONS = {'female':{'s1':['r1','r2'],'s2':['r1']},'male':{'s3':['r3']}}
SECONDARY_REGIONS = {'female':{'s1':['oc1'],'s2':['oc2']},'male':{'s3':['oc3']}}
CONDITIONS = [
    {'name':'female','label':'Female group','color':'#123456','style':'hollow'},
    {'name':'male','label':'Male group','color':'#654321','style':'fill'},
]
POSITION_FIELDS = ['condition','condition_index','animal','animal_index','region','region_index',
                   'column','column_index','factor','factor_value','factor_index','roi_base']
DEFAULTS = {'condition':None,'condition_index':0,'animal':None,'animal_index':0,
    'region':None,'region_index':0,'column':None,'column_index':0,
    'factor':None,'factor_value':None,'factor_index':0,'roi_base':None}


def assert_contract_equal(actual,expected,path=()):
    if isinstance(expected,dict):
        assert isinstance(actual,dict) and actual.keys()==expected.keys(),path
        for name,value in expected.items():
            if name in ['index','index_name','columns','name','condition_index','animal_index',
                        'region_index','column_index','factor_index']:
                assert actual[name]==value,(path,name,actual[name],value)
            else:
                assert_contract_equal(actual[name],value,(*path,name))
    elif isinstance(expected,list):
        assert isinstance(actual,list) and len(actual)==len(expected),(path,'shape')
        for index,(a,b) in enumerate(zip(actual,expected,strict=True)):
            assert_contract_equal(a,b,(*path,index))
    elif isinstance(expected,Real) and not isinstance(expected,bool):
        assert isinstance(actual,Real) and not isinstance(actual,bool),(path,actual,expected)
        if isinstance(expected,Integral):
            assert isinstance(actual,Integral) and actual==expected,(path,actual,expected)
        else:
            assert math.isclose(actual,expected,rel_tol=1e-9,abs_tol=1e-12),(path,actual,expected)
    else:
        assert actual==expected,(path,actual,expected)


def cases():
    rows = []
    def add(method,**state):
        rows.append({'key':f'iteration.{method}.{len(rows)}',
            'capability':'PyFLASH.iteration.Context.'+method,
            'method':method,'state':state})
    for method in ['summary','condition_df','factor_df','animal_df','subject_df']:
        for state in [{},{'condition':'female'},{'condition':'unknown'},
                      {'condition':'female','animal':'s1'},
                      {'condition':'female','animal':'unknown'},
                      {'factor':'Dose','factor_value':0},
                      {'factor':'Sex','factor_value':'female'},
                      {'roi_base':'secondary'},{'roi_base':'missing'}]:
            add(method,**state)
    for method in ['color','style','label']:
        for state in [{},{'condition':'unknown'}, {'condition_obj':'female'}, {'condition_obj':'male'}]:
            add(method,**state)
    for method in ['region_dict','scn_dict','num_conditions','num_animals','num_subjects','num_regions','num_scns']:
        for state in [{},{'condition':'female'},{'condition':'male','animal':'s3'},
                      {'condition':'female','animal':'s1'},
                      {'condition':'unknown','animal':'s1'},
                      {'condition':'female','animal':'s1','roi_base':'secondary'}]:
            add(method,**state)
    for method in ['marker_df']:
        for state in [{},{'condition':'female'},{'animal':'s1'},
                      {'condition':'female','animal':'s1','region':'r2'},
                      {'condition':'male','animal':'s1'},{'region':'r1'}]:
            add(method,**state)
    for method in ['col_values','col_animal_means','col_subject_means']:
        for column in ['Value','Other']:
            for by in ['all','condition','factor']:
                add(method,column=column,condition='female',factor='Dose',factor_value=0,by=by)
                add(method,column=column,condition='female',factor='Dose',factor_value=0,by=by,input_variant='noisy')
    for method in ['scn','scn_index']:
        add(method,region='r2',region_index=3)
        add(method,region='r2',region_index=3,set_value='replacement' if method=='scn' else 7)
    for method in ['iter_conditions','iter_animals','iter_subjects','iter_regions','iter_scns']:
        add(method,condition='female',animal='s1',column='Value')
        if method in ['iter_animals','iter_subjects']:
            add(method,column='Other')
    for factor in ['Sex','Dose']:
        add('iter_factors',factor_name=factor,column='Value')
    add('iter_columns',columns=['Other','Value'],condition='female',animal='s1')
    return rows


def relational(row):
    """Execute full-row selection and means in a separate SQL engine."""
    state,method = row['state'],row['method']
    with sqlite3.connect(':memory:') as db:
        db.execute('CREATE TABLE summary (Position INTEGER, Condition TEXT, Sex TEXT, Dose REAL, Value REAL, Other REAL, AnimalName TEXT)')
        source = [list(v) for v in (NOISY_INPUT if state.get('input_variant')=='noisy' else INPUT)]
        if state.get('roi_base')=='secondary':
            source = [[*v[:3],None if v[3] is None else v[3]*2,v[4],v[5]] for v in source]
        db.executemany('INSERT INTO summary VALUES (?,?,?,?,?,?,?)',[[i,*v] for i,v in enumerate(source)])
        if method=='marker_df':
            db.execute('CREATE TABLE marker (Position INTEGER, AnimalName TEXT, Region TEXT, Object INTEGER, Condition TEXT, Value REAL)')
            db.executemany('INSERT INTO marker VALUES (?,?,?,?,?,?)',[[i,*v] for i,v in enumerate(MARKERS)])
            where,args = [],[]
            for field,column in [('condition','Condition'),('animal','AnimalName'),('region','Region')]:
                if state.get(field) is not None:
                    where.append(column+'=?'); args.append(state[field])
            query = 'SELECT Position,'+','.join(MARKER_COLUMNS)+' FROM marker'
            if where: query += ' WHERE '+' AND '.join(where)
            answer = db.execute(query+' ORDER BY Position',args).fetchall()
            return {'columns':MARKER_COLUMNS,'index':[v[0] for v in answer],
                    'index_name':None,'values':[list(v[1:]) for v in answer],
                    'dtypes':['object','object','int64','object','float64']}
        where,args = [],[]
        selector = method
        if method in ['col_values','col_animal_means','col_subject_means']:
            selector = {'all':'summary','condition':'condition_df','factor':'factor_df'}[state['by']]
        if selector=='subject_df': selector='animal_df'
        if selector=='animal_df':
            selector = 'animal_selection' if state.get('animal') is not None else 'condition_df'
        if selector=='condition_df' and state.get('condition') is not None:
            where,args = ['Condition=?'],[state['condition']]
        elif selector=='factor_df' and state.get('factor') is not None and state.get('factor_value') is not None:
            where,args = [state['factor']+'=?'],[state['factor_value']]
        elif selector=='animal_selection':
            where,args = ['AnimalName=?'],[state['animal']]
        clause = ' WHERE '+' AND '.join(where) if where else ''
        if method in ['col_animal_means','col_subject_means']:
            where.append('AnimalName IS NOT NULL')
            clause = ' WHERE '+' AND '.join(where)
            query = f'SELECT AnimalName,AVG({state["column"]}) FROM summary'+clause
            answer = [v for v in db.execute(query+' GROUP BY AnimalName ORDER BY AnimalName',args).fetchall() if v[1] is not None]
            return {'name':state['column'],'index_name':'AnimalName','dtype':'float64',
                    'index':[v[0] for v in answer],'values':[v[1] for v in answer]}
        if method=='col_values':
            query = f'SELECT AnimalName,{state["column"]} FROM summary'+clause+' ORDER BY Position'
            answer = [v for v in db.execute(query,args).fetchall() if v[1] is not None]
            return {'name':state['column'],'index_name':'SampleID','dtype':'float64',
                    'index':[v[0] for v in answer],'values':[v[1] for v in answer]}
        answer = db.execute('SELECT '+','.join(COLUMNS)+' FROM summary'+clause+' ORDER BY Position',args).fetchall()
        return {'columns':COLUMNS,'dtypes':DTYPES,'index_name':'SampleID','index':[v[-1] for v in answer],
                'values':[list(v) for v in answer]}


def reference(row):
    state,method = row['state'],row['method']
    if method in ['summary','condition_df','factor_df','animal_df','subject_df','marker_df',
                  'col_values','col_animal_means','col_subject_means']:
        return relational(row)
    metadata = next((v for v in CONDITIONS if v['name']==state.get('condition_obj')),None)
    if method in ['color','style','label']:
        return metadata[method] if metadata else {'color':None,'style':'fill','label':state.get('condition') or ''}[method]
    regions = SECONDARY_REGIONS if state.get('roi_base')=='secondary' else REGIONS
    if method in ['region_dict','scn_dict']: return regions
    if method=='num_conditions': return 2
    if method in ['num_animals','num_subjects']: return len(regions.get(state.get('condition'),{}))
    if method in ['num_regions','num_scns']: return len(regions.get(state.get('condition'),{}).get(state.get('animal'),[]))
    if method in ['scn','scn_index']:
        initial = state['region'] if method=='scn' else state['region_index']
        value = state.get('set_value',initial)
        return {'value':value,'region' if method=='scn' else 'region_index':value}
    position = DEFAULTS|{k:v for k,v in state.items() if k in DEFAULTS}
    children = []
    if method=='iter_conditions':
        children = [position|{'condition':name,'condition_index':i,'condition_obj':name}
                    for i,name in enumerate(['female','male'])]
    elif method in ['iter_animals','iter_subjects']:
        if state.get('condition')=='female':
            children = [position|{'animal':name,'animal_index':i,'condition_obj':None}
                        for i,name in enumerate(['s1','s2'])]
        else:
            children = [position|{'condition':'female','condition_index':0,'condition_obj':'female','animal':'s1','animal_index':0},
                        position|{'condition':'female','condition_index':0,'condition_obj':'female','animal':'s2','animal_index':1},
                        position|{'condition':'male','condition_index':1,'condition_obj':'male','animal':'s3','animal_index':2}]
    elif method in ['iter_regions','iter_scns']:
        children = [position|{'region':r,'region_index':i,'condition_obj':None} for i,r in enumerate(['r1','r2'])]
    elif method=='iter_factors':
        name = state['factor_name']
        expected = ['female','male'] if name=='Sex' else [2.,1.,0.]
        children = [position|{'factor':name,'factor_value':v,'factor_index':i,'condition_obj':None}
                    for i,v in enumerate(expected)]
    elif method=='iter_columns':
        children = [position|{'column':name,'column_index':i,'condition_obj':None}
                    for i,name in enumerate(['Other','Value'])]
    else:
        raise ValueError(method)
    return children


def exact_subject_means(row):
    """Second arithmetic benchmark: exact fractions, no SQL or pandas means."""
    state = row['state']
    grouped = {}
    for record in (NOISY_INPUT if state.get('input_variant')=='noisy' else INPUT):
        values = dict(zip(COLUMNS,record))
        if state['by']=='condition' and values['Condition']!=state['condition']: continue
        if state['by']=='factor' and values[state['factor']]!=state['factor_value']: continue
        value = values[state['column']]
        if value is not None and values['AnimalName'] is not None:
            grouped.setdefault(values['AnimalName'],[]).append(Fraction(value))
    names = sorted(grouped)
    return {'name':state['column'],'index_name':'AnimalName','dtype':'float64','index':names,
            'values':[float(sum(grouped[k])/len(grouped[k])) for k in names]}


def production(row):
    import pandas as pd
    from PyFLASH.iteration import Context
    frame = pd.DataFrame(NOISY_INPUT if row['state'].get('input_variant')=='noisy' else INPUT,columns=COLUMNS)
    frame.index = pd.Index(frame['AnimalName'],name='SampleID')
    secondary = frame.copy(deep=True)
    secondary['Value'] *= 2
    marker = pd.DataFrame(MARKERS,columns=MARKER_COLUMNS).set_index(['AnimalName','Region','Object'])
    conditions = [SimpleNamespace(**v) for v in CONDITIONS]
    primary_regions,secondary_regions = deepcopy(REGIONS),deepcopy(SECONDARY_REGIONS)
    originals = [v.copy(deep=True) for v in (frame,secondary,marker)]
    target = SimpleNamespace(summary=frame,summaries={'secondary':secondary},condition_list=conditions,
        data={'signal':SimpleNamespace(df=marker)},
        getRegionDict=lambda roi_base=None:secondary_regions if roi_base=='secondary' else primary_regions)
    state = row['state']
    kwargs = {k:v for k,v in state.items() if k in DEFAULTS}
    if 'condition_obj' in state:
        kwargs['condition_obj'] = next(c for c in conditions if c.name==state['condition_obj'])
    context = Context(target,**kwargs)
    method = row['method']
    if method=='marker_df': result=context.marker_df('signal')
    elif method in ['col_values','col_animal_means','col_subject_means']:
        result=getattr(context,method)(by=state['by'])
    elif method in ['iter_conditions','iter_animals','iter_subjects','iter_regions','iter_scns']:
        result=list(getattr(context,method)())
    elif method=='iter_factors': result=list(context.iter_factors(state['factor_name']))
    elif method=='iter_columns': result=list(context.iter_columns(state['columns']))
    elif method in ['scn','scn_index']:
        if 'set_value' in state: setattr(context,method,state['set_value'])
        result = {'value':getattr(context,method),
                'region' if method=='scn' else 'region_index':context.region if method=='scn' else context.region_index}
    else: result=getattr(context,method)
    for actual,before in zip((frame,secondary,marker),originals,strict=True):
        pd.testing.assert_frame_equal(actual,before)
    assert primary_regions==REGIONS and secondary_regions==SECONDARY_REGIONS
    def clean(v):
        return None if isinstance(v,float) and math.isnan(v) else v
    if isinstance(result,pd.DataFrame):
        return {'columns':list(result.columns),'dtypes':[str(t) for t in result.dtypes],
                'index_name':result.index.name,'index':list(result.index),
                'values':[[clean(v) for v in values] for values in result.to_numpy().tolist()]}
    if isinstance(result,pd.Series):
        return {'name':result.name,'dtype':str(result.dtype),'index_name':result.index.name,'index':list(result.index),
                'values':[clean(v) for v in result.tolist()]}
    if isinstance(result,list) and result and isinstance(result[0],Context):
        return [{**{k:getattr(v,k) for k in POSITION_FIELDS},
                 'condition_obj':v.condition_obj.name if v.condition_obj else None} for v in result]
    return result
