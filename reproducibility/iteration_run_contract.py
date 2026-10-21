"""Independent event traces and database-selected rows for action orchestration."""
from pathlib import Path
from types import SimpleNamespace
from copy import deepcopy
import sqlite3
from reproducibility.iteration_contract import INPUT, COLUMNS, REGIONS, CONDITIONS, POSITION_FIELDS, DEFAULTS

FIXTURE = Path(__file__).parent/'fixtures/iteration_run_reference.json'


def cases():
    levels = [['conditions'],['subjects'],['animals'],['columns'],['factors'],
        ['conditions','subjects'],['conditions','animals','regions'],
        ['conditions','subjects','scns'],['columns','conditions'],['conditions','columns'],
        ['conditions','conditions'],['subjects','columns'],['factors','columns'],[]]
    rows = []
    for over in levels:
        for variant in ['plain','filtered','labels','secondary','skip','hooks']:
            rows.append({'key':f'iteration.run.{len(rows)}','capability':'PyFLASH.iteration.run',
                'parameters':{'over':over,'variant':variant,'columns':['Other','Value'],'factor':'Sex'}})
    for level in ['conditions','animals','subjects','columns','factors']:
        for variant in ['plain','hooks','filtered']:
            rows.append({'key':f'iteration.apply_per.{len(rows)}','capability':'PyFLASH.iteration.apply_per',
                'parameters':{'over':[level],'variant':variant,'columns':['Other','Value'],'factor':'Sex'}})
    return rows


def selected_values(state, parameters):
    with sqlite3.connect(':memory:') as database:
        database.execute('CREATE TABLE samples(Condition TEXT,Sex TEXT,Dose REAL,Value REAL,Other REAL,AnimalName TEXT)')
        records = deepcopy(INPUT)
        if parameters['variant']=='secondary':
            for row in records:
                if row[3] is not None: row[3] *= 2
        database.executemany('INSERT INTO samples VALUES (?,?,?,?,?,?)',records)
        clauses, values = [],[]
        if parameters['variant']=='filtered': clauses.append('Sex=?'); values.append('female')
        if state['animal'] is not None: clauses.append('AnimalName=?');values.append(state['animal'])
        elif state['condition'] is not None: clauses.append('Condition=?');values.append(state['condition'])
        clause = ' WHERE '+' AND '.join(clauses) if clauses else ''
        answer = database.execute('SELECT '+','.join(COLUMNS)+' FROM samples'+clause,values).fetchall()
        return [list(row) for row in answer]


def reference(row):
    parameters = row['parameters']
    variant, over = parameters['variant'],parameters['over']
    root = DEFAULTS|{'roi_base':'secondary' if variant=='secondary' else None,'condition_obj':None}
    events, results = [],{}
    visits = 0

    def children(position, level):
        if level=='conditions':
            return [position|{'condition':name,'condition_obj':name,'condition_index':j}
                    for j,name in enumerate(['female','male'])]
        if level in ['animals','subjects']:
            if position['condition'] is not None:
                return [position|{'animal':name,'animal_index':j}
                    for j,name in enumerate(REGIONS.get(position['condition'],{}))]
            return [position|{'condition':'female','condition_obj':'female','condition_index':0,'animal':'s1','animal_index':0},
                    position|{'condition':'female','condition_obj':'female','condition_index':0,'animal':'s2','animal_index':1},
                    position|{'condition':'male','condition_obj':'male','condition_index':1,'animal':'s3','animal_index':2}]
        if level in ['regions','scns']:
            return [position|{'region':region,'region_index':j}
                    for j,region in enumerate(REGIONS[position['condition']][position['animal']])]
        if level=='columns':
            return [position|{'column':name,'column_index':j} for j,name in enumerate(parameters['columns'])]
        if level=='factors':
            names = ['female'] if variant=='filtered' else ['female','male']
            return [position|{'factor':'Sex','factor_value':name,'factor_index':j} for j,name in enumerate(names)]
        raise ValueError(level)

    def recurse(position, depth):
        nonlocal visits
        if depth==len(over):
            visits += 1
            events.append({'kind':'action','position':position,'visit':visits,
                           'rows':selected_values(position,parameters),
                           'label':None if position['column'] is None else
                                   ('Custom '+position['column'] if variant=='labels' else position['column']),
                           'token':'passed-through'})
            if variant!='skip' or visits%2==0:
                results.setdefault('position',[]).append(position)
                results.setdefault('visit',[]).append(visits)
            return
        for child in children(position,over[depth]):
            if depth==0 and variant=='hooks': events.append({'kind':'setup','position':child,'visits':visits})
            recurse(child,depth+1)
            if depth==0 and variant=='hooks':
                events.append({'kind':'teardown','position':child,'visits':visits,'result_count':len(results.get('visit',[]))})
    recurse(root,0)
    return {'events':events,'results':results,'total_visits':visits}


def production(row):
    import pandas as pd
    from PyFLASH.iteration import run,apply_per
    from PyFLASH.plotting import get_display_name
    parameters = row['parameters']
    variant = parameters['variant']
    frame = pd.DataFrame(INPUT,columns=COLUMNS)
    frame.index = pd.Index(frame['AnimalName'],name='SampleID')
    secondary = frame.copy(deep=True)
    secondary['Value'] *= 2
    original_frames = [frame.copy(deep=True),secondary.copy(deep=True)]
    regions = deepcopy(REGIONS)
    class Target:
        @property
        def summary(self): return self.summaries['primary']
    target = Target()
    target.summaries = {'primary':frame,'secondary':secondary}
    original_summaries = target.summaries
    target.condition_list = [SimpleNamespace(**record) for record in CONDITIONS]
    target.getRegionDict = lambda roi_base=None: regions
    events, visits = [],0
    def position(context):
        return {**{name:getattr(context,name) for name in POSITION_FIELDS},
                'condition_obj':context.condition_obj.name if context.condition_obj else None}
    def action(context,state,token):
        nonlocal visits
        visits += 1
        state['visits'] = visits
        # Animal selection is independent of a conflicting condition. This
        # explicit lookup exercises the public row-access API as well as events.
        data = context.animal_df if context.animal is not None else context.condition_df
        data = [[None if pd.isna(v) else v for v in values] for values in data.to_numpy().tolist()]
        events.append({'kind':'action','position':position(context),'visit':visits,
            'rows':data,'label':None if context.column is None else get_display_name(context.column),'token':token})
        return None if variant=='skip' and visits%2 else {'position':position(context),'visit':visits}
    kwargs = {'columns':parameters['columns'],'factor':parameters['factor'],'token':'passed-through'}
    if variant=='filtered': kwargs['specificity'] = ('Sex','female')
    if variant=='secondary': kwargs['roi_base'] = 'secondary'
    if variant=='labels': kwargs['column_labels'] = {'Other':'Custom Other','Value':'Custom Value'}
    if variant=='hooks':
        kwargs['setup'] = lambda ctx,state: events.append({'kind':'setup','position':position(ctx),'visits':state.get('visits',0)})
        kwargs['teardown'] = lambda ctx,state,result: events.append({'kind':'teardown','position':position(ctx),'visits':state.get('visits',0),'result_count':len(result.get('visit',[]))})
    result = (apply_per(target,parameters['over'][0],action,**kwargs) if row['capability'].endswith('apply_per')
              else run(target,parameters['over'],action,**kwargs))
    assert target.summaries is original_summaries
    for current,before in zip((frame,secondary),original_frames,strict=True):
        pd.testing.assert_frame_equal(current,before)
    assert regions == REGIONS
    return {'events':events,'results':result,'total_visits':visits}
