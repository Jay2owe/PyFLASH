"""Candidate-free native R answers for every ordered experiment marker pair.

The experiment-level reference is a composition of the original published
distance kernel and explicit native-R grouping/attribution policies. It is not
a second published complete microscopy workflow.
"""
import copy
import json
import math
from pathlib import Path
from reproducibility import marker_nearest_reference as original


def specifications():
    cases=original.cases()
    result=[]
    for case in cases:
        result.append({'key':'experiment-nearest.two.'+case['key'],
            'threshold':case['threshold'],'markers':[
                {'name':'L','class':'object','side':'left','case':copy.deepcopy(case)},
                {'name':'R','class':'cell','side':'right','case':copy.deepcopy(case)}]})
    for case in cases[:12]:
        third=copy.deepcopy(case)
        third['coloc_column']=None
        for row in third['left']:
            if row['point'][0] is not None and math.isfinite(float(row['point'][0])):
                row['point'][0]+=0.125
        result.append({'key':'experiment-nearest.three.'+case['key'],
            'threshold':case['threshold'],'markers':[
                {'name':'L','class':'object','side':'left','case':copy.deepcopy(case)},
                {'name':'R','class':'cell','side':'right','case':copy.deepcopy(case)},
                {'name':'T','class':'object','side':'left','case':third}]})
    archive=Path(original.__file__).with_name('reference-sources')/'marker-calibration/native-imagej-v1/native.json'
    native=json.loads(archive.read_text(encoding='utf-8'))
    for pitch in range(3):
        acquired=native['cases'][2*pitch:2*pitch+2]
        case={'key':f'experiment-nearest.calibrated-{pitch}',
              'threshold':30,'coloc_column':None,'index_group':'Region',
              'left_groups':['Region','AnimalName','Condition'],
              'right_groups':['Region','AnimalName','Condition']}
        for side,item in zip(('left','right'),acquired,strict=True):
            case[side]=[{'Region':'SCN1','AnimalName':'Subject1','Condition':'Subject',
                         'point':item['physical_centre']}]
        result.append({'key':case['key'],'threshold':30,'markers':[
            {'name':'L','class':'object','side':'left','case':case,'native':acquired[0]},
            {'name':'R','class':'cell','side':'right','case':case,'native':acquired[1]}]})
    result.append({'key':'experiment-nearest.no-spatial-markers','threshold':30,'markers':[]})
    for cls in ('object','cell'):
        result.append({'key':'experiment-nearest.one-'+cls,'threshold':cases[0]['threshold'],
            'markers':[{'name':'L','class':cls,'side':'left','case':copy.deepcopy(cases[0])}]})
    return result


def pair_cases(specification):
    result=[]
    for source in specification['markers']:
        for target in specification['markers']:
            if source['name']==target['name']:continue
            left,right=source['case'],target['case']
            result.append({'key':specification['key']+'.'+source['name']+'-to-'+target['name'],
                'source':source['name'],'target':target['name'],
                'left':copy.deepcopy(left[source['side']]),
                'right':copy.deepcopy(right[target['side']]),
                'left_groups':list(left[source['side']+'_groups']),
                'right_groups':list(right[target['side']+'_groups']),
                'coloc_column':left['coloc_column'] if source['name']=='L' and target['name']=='R' else None,
                'threshold':specification['threshold']})
    return result


def queries(specifications):
    return [original.query(case) for item in specifications for case in pair_cases(item)]


def encode(value):
    if isinstance(value,float) and not math.isfinite(value):
        return '__nan__' if math.isnan(value) else '__inf__' if value>0 else '__neginf__'
    if isinstance(value,list):return [encode(item) for item in value]
    if isinstance(value,dict):return {key:encode(item) for key,item in value.items()}
    return value


def answers(specifications,native_rows,values):
    iterator=iter(native_rows)
    result=[]
    for specification in specifications:
        pairs=[]
        for case in pair_cases(specification):
            native=next(iterator)
            assert native['key']==case['key']
            pairs.append({'case':case,'expected':encode(original.unpack(case,list(values(native))))})
        result.append({'specification':specification,'pairs':pairs})
    assert next(iterator,None) is None
    return result
