"""Literal full group-design definitions, independent Cartesian products/pairs."""
from pathlib import Path
from copy import deepcopy
from itertools import product, combinations

FIXTURE = Path(__file__).parent/'fixtures/conditions_contract_reference.json'
ENTRIES = [
    {'label':'Female','name':'F','color':'#123456','style':'hollow','factor':'Sex','factor_explanation':None},
    {'label':'Male','name':'M','color':'#654321','style':'fill','factor':'Sex','factor_explanation':None},
    {'label':'Other','name':'X','color':'#ABCDEF','style':'///','factor':'Sex','factor_explanation':None},
]
TREATMENTS = [
    {'label':'Control','name':'C','color':'#112233','style':'fill','factor':'Treatment','factor_explanation':None},
    {'label':'Drug','name':'D','color':'#445566','style':'fill','factor':'Treatment','factor_explanation':None},
]


def cases():
    rows = []
    single_operations = ['plain','all','control','sequential','pair','combined','explain','auto','css','default_short']
    for operation in single_operations:
        capabilities = ['ConditionBuilder.add','ConditionBuilder.build']
        if operation in ['all','combined']: capabilities += ['ConditionBuilder.compare_all_pairs']
        if operation in ['control','combined']: capabilities += ['ConditionBuilder.compare_to_control']
        if operation in ['sequential','combined']: capabilities += ['ConditionBuilder.compare_sequential']
        if operation in ['pair','combined']: capabilities += ['ConditionBuilder.compare']
        if operation=='explain': capabilities += ['ConditionBuilder.explain']
        rows.append({'key':'conditions.single.'+operation,'capability':'PyFLASH.conditions.ConditionBuilder.build',
                     'capabilities':['PyFLASH.conditions.'+v for v in capabilities],
                     'parameters':{'kind':'single','operation':operation}})
    for ordering,comparison,colors,explain in product(['Sex','Treatment'],
        ['none','all','within','control_within','pair_within'],[False,True],[False,True]):
        capabilities = ['ConditionBuilder.add','ConditionBuilder.build','ConditionBuilder.cross',
                        '_CrossedConditionBuilder.order_by','_CrossedConditionBuilder.build']
        if comparison in ['all','within']: capabilities += ['_CrossedConditionBuilder.compare_all_pairs']
        if comparison=='control_within': capabilities += ['_CrossedConditionBuilder.compare_to_control']
        if comparison=='pair_within': capabilities += ['_CrossedConditionBuilder.compare']
        if explain: capabilities += ['_CrossedConditionBuilder.explain']
        rows.append({'key':f'conditions.cross.{ordering}.{comparison}.{colors}.{explain}',
            'capability':'PyFLASH.conditions._CrossedConditionBuilder.build',
            'capabilities':['PyFLASH.conditions.'+v for v in capabilities],
            'parameters':{'kind':'cross','ordering':ordering,'comparison':comparison,'colors':colors,'explain':explain}})
    for method in ['zipConditions','zipConditionLists']:
        rows.append({'key':'conditions.legacy.'+method,'capability':'PyFLASH.conditions.'+method,
            'capabilities':['PyFLASH.conditions.'+method], 'parameters':{'kind':method}})
    for comparison in ['control_all','pair_all']:
        operation = 'compare_to_control' if comparison=='control_all' else 'compare'
        rows.append({'key':'conditions.cross.singleton.'+comparison,
            'capability':'PyFLASH.conditions._CrossedConditionBuilder.'+operation,
            'capabilities':['PyFLASH.conditions.ConditionBuilder.cross',
                'PyFLASH.conditions._CrossedConditionBuilder.'+operation,
                'PyFLASH.conditions._CrossedConditionBuilder.build'],
            'parameters':{'kind':'cross','ordering':None,'comparison':comparison,'colors':False,
                          'explain':False,'right_length':1}})
    return rows


def reference(row):
    parameters = row['parameters']
    left,right = deepcopy(ENTRIES),deepcopy(TREATMENTS)
    right = right[:parameters.get('right_length',len(right))]
    if parameters['kind'] in ['single','zipConditions']:
        operation = parameters.get('operation','plain')
        if operation=='auto':
            for entry,color in zip(left,['#E69F00','#56B4E9','#009E73']): entry['color']=color
        if operation=='css':
            for entry in left: entry['color']='#4682b4'
        if operation=='default_short':
            for entry in left: entry['name']=entry['label']
        if operation=='explain':
            for entry in left: entry['factor_explanation']='Group '+entry['label']
        pairs = []
        if operation in ['all','combined']: pairs += [(1,2),(1,3),(2,3)]
        if operation in ['control','combined']: pairs += [(2,1),(2,3)]
        if operation in ['sequential','combined']: pairs += [(1,2),(2,3)]
        if operation in ['pair','combined']: pairs += [(3,1)]
        if parameters['kind']=='zipConditions':
            for entry in left: entry['style']='fill'
            return left
        return {'conditions':left,'components':left,'factor':['Sex'],
                'factorDict':{'Sex':[entry['name'] for entry in left]},
                'comparisons':[f'{a}-{b}' for a,b in pairs] or None}
    crossed = []
    for a,b in product(left,right):
        components = [deepcopy(a),deepcopy(b)]
        crossed.append({'name':a['name']+b['name'],'label':a['label']+b['label'],
            'color':a['color'],'style':a['style'],'factor':['Sex','Treatment'],
            'factor_explanation':[None,None],'components':components})
    if parameters.get('colors'):
        for j,entry in enumerate(crossed): entry['color']=['#010101','#020202','#030303','#040404','#050505','#060606'][j]
    if parameters['kind']=='zipConditionLists': return crossed
    if parameters['ordering']=='Treatment':
        crossed.sort(key=lambda entry:entry['components'][1]['name'])
    if parameters['explain']:
        for entry in crossed:
            for component in entry['components']:
                component['factor_explanation']='Cross '+component['label']
            entry['factor_explanation']=[component['factor_explanation'] for component in entry['components']]
    comparison = parameters['comparison']
    pairs = []
    if comparison=='all': pairs = list(combinations(range(1,7),2))
    if comparison=='control_all': pairs = [(1,2),(1,3)]
    if comparison=='pair_all': pairs = [(1,2)]
    if comparison in ['within','control_within','pair_within']:
        for treatment in ['C','D']:
            indexes = [j+1 for j,entry in enumerate(crossed) if entry['components'][1]['name']==treatment]
            if comparison=='within': pairs += list(combinations(indexes,2))
            if comparison=='control_within': pairs += [(indexes[0],j) for j in indexes[1:]]
            if comparison=='pair_within' and treatment=='C': pairs += [(indexes[0],indexes[1])]
    return {'conditions':crossed,'components':[part for entry in crossed for part in entry['components']],
        'factor':['Sex','Treatment'], 'factorDict':{
            'Sex':list(dict.fromkeys(entry['components'][0]['name'] for entry in crossed)),
            'Treatment':list(dict.fromkeys(entry['components'][1]['name'] for entry in crossed))},
        'comparisons':[f'{a}-{b}' for a,b in pairs] or None}


def production(row):
    from PyFLASH.conditions import ConditionBuilder,zipConditions,zipConditionLists
    parameters = row['parameters']
    def make(entries,operation='plain'):
        builder = ConditionBuilder(entries[0]['factor'])
        for entry in entries:
            color = None if operation=='auto' else 'steelblue' if operation=='css' else entry['color']
            result = builder.add(entry['label'],short=None if operation=='default_short' else entry['name'],
                                 color=color,style=entry['style'])
            assert result is builder
        if operation in ['all','combined']: assert builder.compare_all_pairs() is builder
        if operation in ['control','combined']: assert builder.compare_to_control('M') is builder
        if operation in ['sequential','combined']: assert builder.compare_sequential() is builder
        if operation in ['pair','combined']: assert builder.compare('X','F') is builder
        if operation=='explain': assert builder.explain('Group <>') is builder
        return builder.build()
    def entry(c):
        result = {k:getattr(c,k) for k in ['label','name','color','style','factor','factor_explanation']}
        if hasattr(c,'conditionsList'): result['components'] = [entry(v) for v in c.conditionsList]
        return result
    if parameters['kind']=='zipConditions':
        return [entry(c) for c in zipConditions([e['label'] for e in ENTRIES],
                 [e['name'] for e in ENTRIES],[e['color'] for e in ENTRIES],'Sex')]
    if parameters['kind']=='single': result = make(ENTRIES,parameters['operation'])
    else:
        left,right = make(ENTRIES),make(TREATMENTS[:parameters.get('right_length',len(TREATMENTS))])
        before_left,before_right = [entry(c) for c in left],[entry(c) for c in right]
        if parameters['kind']=='zipConditionLists': return [entry(c) for c in zipConditionLists(left,right)]
        builder = ConditionBuilder.cross(left,right,colors=['#010101','#020202','#030303','#040404','#050505','#060606'] if parameters['colors'] else None)
        assert builder.order_by(parameters['ordering']) is builder
        comparison = parameters['comparison']
        if comparison=='all': assert builder.compare_all_pairs() is builder
        if comparison=='within': assert builder.compare_all_pairs(within_factor='Treatment') is builder
        if comparison=='control_within': assert builder.compare_to_control('F',within_factor='Treatment') is builder
        if comparison=='pair_within': assert builder.compare('F','M',within='C') is builder
        if comparison=='control_all': assert builder.compare_to_control('F') is builder
        if comparison=='pair_all': assert builder.compare('F','M') is builder
        if parameters['explain']: assert builder.explain('Cross <>') is builder
        result = builder.build()
        assert [entry(c) for c in left]==before_left
        assert [entry(c) for c in right]==before_right
    return {'conditions':[entry(c) for c in result], 'components':[entry(c) for c in result.conditions],
        'factor':result.factor,'factorDict':{k:[c.name for c in v] for k,v in result.factorDict.items()},
        'comparisons':result.comparisons}
