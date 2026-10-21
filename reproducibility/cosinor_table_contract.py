"""Complete public rows composed from independently frozen rhythm references.

The parent input/identity contract has a separate raw-input R comparison. Child
answers are reused only when all retained time/value/subject inputs match; this
composition adds no independent scientific-reference family or child fit vote.
"""
from pathlib import Path
import copy, hashlib, json, math, re
from reproducibility import cosinor_contract as pooled
from reproducibility import population_rhythm_contract as population
from reproducibility import mixed_rhythm_contract as mixed
from reproducibility.reference_runtime import execute_queries, values

FIXTURE = Path(__file__).with_name('fixtures') / 'cosinor_table_reference.json'
FIELDS = ['group','n','method','mesor','amplitude','acrophase','period',
          'r_squared','p_rhythm','amplitude_se','acrophase_se','error']
DEPENDENCIES = [pooled.FIXTURE, population.FIXTURE, mixed.FIXTURE,
                Path(pooled.__file__), Path(population.__file__), Path(mixed.__file__)]

def dependencies():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in DEPENDENCIES}

def _children():
    return {method: json.loads(module.FIXTURE.read_text(encoding='utf-8'))['rows']
            for method,module in [('pooled',pooled),('population_mean',population),('mixed',mixed)]}

def cases():
    out=[]
    for method,children in _children().items():
        for child in children:
            p=child['parameters']
            if method=='pooled':
                if p['period_free'] and p.get('free_bounds') != [p['period']*2/3,p['period']*1.5]:
                    continue
                records=[[t,y,'A','Subject'] for t,y in zip(p['t'],p['y'])]
            else:
                records=[[t,y,'A',a] for t,y,a in p['records']]
            base={'key':'cosinor-table.'+child['key'], 'capability':'PyFLASH.stats_extra.cosinor_table',
                  'parameters':{'columns':['time','value','group','animal'],'records':records,
                                'time_col':'time','value_col':'value','group_col':'group','animal_col':'animal',
                                'method':method,'period':p['period'],'period_free':p.get('period_free',False)},
                  'child_key':child['key']}
            out.append(base)
        # Exercise every preprocessing option on the same frozen child input.
        seed=next(r for r in out if r['parameters']['method']==method
                  and not r['parameters']['period_free'] and r['parameters']['period']==24.)
        variants=[]
        for column in ['_t','_v','_grp','_animal',0]:
            for field in ['time_col','value_col','group_col','animal_col']:
                row=copy.deepcopy(seed); index=['time_col','value_col','group_col','animal_col'].index(field)
                row['parameters']['columns'][index]=column;row['parameters'][field]=column
                variants.append((f'{field}.{column}',row))
        row=copy.deepcopy(seed);row['parameters']['group_col']=None;variants.append(('ungrouped',row))
        row=copy.deepcopy(seed);row['parameters'].pop('period');variants.append(('default-period',row))
        row=copy.deepcopy(seed)
        row['parameters']['records'] += [[None,9.,'A','Subject'],[0.,None,'A','Subject'],
                                        ['Inf',8.,'A','Subject'],[0.,'Inf','A','Subject'],
                                        [0.,9.,None,'Subject']]
        if method!='pooled':row['parameters']['records'] += [[0.,9.,'A',None]]
        variants.append(('invalid-pairs-and-identities',row))
        row=copy.deepcopy(seed);row['parameters']['records']=list(reversed(row['parameters']['records']))
        variants.append(('reversed',row))
        for mode in ['labels','mapped','unmatched-map','partial-map']:
            row=copy.deepcopy(seed);p=row['parameters'];mapping={}
            if mode in ['labels','unmatched-map'] and any(number(r[0])<0 for r in p['records']):
                positive=next(r for r in out if r['parameters']['method']==method
                              and r['child_key']=='cosinor.fixed.exact_peak_quarter')
                row=copy.deepcopy(positive);p=row['parameters']
            for record in p['records']:
                label='ZT'+str(record[0]);mapping[label]=record[0];record[0]=label
            if mode=='mapped':p['time_map']=mapping
            elif mode=='unmatched-map':p['time_map']={'absent':999.}
            elif mode=='partial-map':
                p['records'].append(['not mapped',900.,'A','Subject']);p['time_map']=mapping
            variants.append((mode,row))
        row=copy.deepcopy(seed)
        row['parameters']['records'] += [[t,y,'B',a] for t,y,g,a in row['parameters']['records']]
        variants.append(('two-groups',row))
        for tag,row in variants:
            row['key']=seed['key']+'.'+tag;out.append(row)
        for tag,records in [('empty',[]),('all-missing',[[None,None,'A','Subject']]),
                            ('missing-groups',[[0.,1.,None,'Subject']])]:
            row=copy.deepcopy(seed);row['parameters']['records']=records;row['key']=seed['key']+'.'+tag
            out.append(row)
    return out

def number(value):
    try:return float(value) if value is not None else math.nan
    except (TypeError,ValueError):return math.nan

def prepared(row):
    p=row['parameters'];columns=p['columns'];raw=p['records']
    times=[r[columns.index(p['time_col'])] for r in raw]
    mapping=p.get('time_map') or {};mapped=[mapping.get(t) for t in times]
    if any(t is not None and not math.isnan(number(t)) for t in mapped):
        ts=[number(t) for t in mapped]
    elif any(not math.isnan(number(t)) for t in times):ts=[number(t) for t in times]
    else:
        matches=[re.search(r'(\d+\.?\d*)',str(t)) for t in times]
        ts=[number(m.group(0)) if m else math.nan for m in matches]
    result=[]
    for t,record in zip(ts,raw):
        y=number(record[columns.index(p['value_col'])])
        group=record[columns.index(p['group_col'])] if p.get('group_col') is not None else 'all'
        animal=record[columns.index(p['animal_col'])] if p.get('animal_col') is not None else None
        if not math.isfinite(t) or not math.isfinite(y) or group is None:continue
        if p['method']!='pooled' and animal is None:continue
        result.append([t,y,str(group),animal])
    return result

def columns(row):
    return FIELDS+(['n_subjects'] if row['parameters']['method']=='population_mean' else [])

def expected(row):
    p=row['parameters'];child=next(r for r in _children()[p['method']] if r['key']==row['child_key'])
    cp=child['parameters'];answer=values(child['mathematical']);data=prepared(row);records=[]
    if p['method']=='pooled':child_data=sorted([[t,y] for t,y in pooled.paired(cp)])
    else:
        raw=population.finite_records(child) if p['method']=='population_mean' else mixed.prepared(child)
        child_data=sorted([[t,y,a] for t,y,a in raw])
    for g in dict.fromkeys(r[2] for r in data):
        sub=[r for r in data if r[2]==g]
        actual_data=sorted([[r[0],r[1]]+([r[3]] if p['method']!='pooled' else []) for r in sub])
        if actual_data!=child_data:raise ValueError('Cannot reuse reference for different retained inputs: '+row['key'])
        rec=dict.fromkeys(columns(row),math.nan)
        rec.update(group=g,n=len(sub),method=p['method'],error=None)
        if p['method']=='pooled':
            offset=1 if cp['period_free'] else 0
            rec.update(mesor=answer[2],amplitude=answer[3],acrophase=answer[4],period=answer[1],
                       amplitude_se=answer[8],acrophase_se=answer[9],r_squared=answer[10+offset],p_rhythm=answer[12+offset])
        else:
            rec.update(zip(population.FIELDS if p['method']=='population_mean' else mixed.FIELDS,answer))
        records.append(rec)
    return {'columns':columns(row),'records':records}

def production(row):
    import pandas as pd
    from PyFLASH.stats_extra import cosinor_table
    p=row['parameters'];options={k:v for k,v in p.items() if k not in ['columns','records']}
    table=cosinor_table(pd.DataFrame(p['records'],columns=p['columns']),**options)
    return {'columns':list(table.columns),'records':table.to_dict(orient='records')}

def packed(value):
    if isinstance(value,float) and not math.isfinite(value):return {'nonfinite':'nan' if math.isnan(value) else 'positive_infinity' if value>0 else 'negative_infinity'}
    if isinstance(value,dict):return {k:packed(v) for k,v in value.items()}
    if isinstance(value,list):return [packed(v) for v in value]
    return value

def equal(actual,reference):
    if type(actual)!=type(reference) and not isinstance(actual,(int,float)):return False
    if isinstance(reference,dict):
        if actual.keys()!=reference.keys() or not all(equal(actual[k],v) for k,v in reference.items()):return False
        if isinstance(reference.get('p_rhythm'),float) and reference['p_rhythm']>0:
            return math.isclose(actual['p_rhythm'],reference['p_rhythm'],rel_tol=1e-9,abs_tol=0.)
        return True
    if isinstance(reference,list):return len(actual)==len(reference) and all(equal(a,b) for a,b in zip(actual,reference))
    if isinstance(reference,float):
        if math.isnan(reference):return isinstance(actual,(int,float)) and math.isnan(actual)
        return math.isclose(actual,reference,rel_tol=1e-9,abs_tol=1e-12)
    return actual==reference

def native_query(row):
    p=row['parameters'];cs=p['columns'];rs=p['records']
    def vector(xs):
        return 'c('+','.join('NA_character_' if x is None else json.dumps(str(x)) for x in xs)+')' if xs else 'character(0)'
    t=vector([r[cs.index(p['time_col'])] for r in rs]);y=vector([r[cs.index(p['value_col'])] for r in rs])
    g=vector([r[cs.index(p['group_col'])] for r in rs]) if p.get('group_col') is not None else f'rep("all",length(t))'
    a=vector([r[cs.index(p['animal_col'])] for r in rs])
    mapping=p.get('time_map') or {};mapcode='numeric(0)' if not mapping else 'setNames(c('+','.join(format(v,'.17g') for v in mapping.values())+'),'+vector(list(mapping))+')'
    return f'''local({{
      t<-{t};y<-{y};g<-{g};a<-{a};mapping<-{mapcode};
      mt<-mapping[t];nt<-suppressWarnings(as.numeric(t));
      if(any(!is.na(mt))) t<-as.numeric(mt) else if(any(!is.na(nt))) t<-nt else {{
        hit<-regexpr("[0-9]+\\\\.?[0-9]*",t);txt<-rep(NA_character_,length(t));
        found<-!is.na(hit)&hit>0;txt[found]<-regmatches(t,hit);t<-suppressWarnings(as.numeric(txt));
      }}
      y<-suppressWarnings(as.numeric(y));keep<-(is.finite(t)&is.finite(y)&!is.na(g)
        {"&!is.na(a)" if p['method']!='pooled' else ''});
      t<-t[keep];y<-y[keep];g<-g[keep];a<-a[keep];
      as.vector(rbind(t,y,match(g,unique(g)),match(a,unique(a))))
    }})'''

def preprocessing_answer(row):
    data=prepared(row);gs=list(dict.fromkeys(r[2] for r in data));animals=list(dict.fromkeys(r[3] for r in data))
    return [v for t,y,g,a in data for v in [t,y,gs.index(g)+1,animals.index(a)+1]]

def check_identity():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'))
    if fixture['dependencies']!=dependencies():raise ValueError('Composed reference dependencies changed')
    if fixture['reference_code_sha256']!=hashlib.sha256(Path(__file__).read_bytes()).hexdigest():raise ValueError('Parent reference source changed')
    if cases()!=[r['case'] for r in fixture['rows']]:raise ValueError('Parent input definitions changed')
    queries=[{'key':r['key'],'code':native_query(r)} for r in cases()]
    if queries!=[{k:r[k] for k in q} for q,r in zip(queries,fixture['native']['rows'],strict=True)]:raise ValueError('Native raw preprocessing expressions changed')
    return fixture,queries

def execute(output):
    fixture,queries=check_identity();result=execute_queries(queries,output,name='cosinor-table-raw-preprocessing')
    for key in ['R','webR','wasm_sha256']:
        if result[key]!=fixture['native'][key]:raise ValueError('Parent native runtime changed')
    return result
