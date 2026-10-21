"""Complete declared constant-fit outlier and subject-report contracts."""
from pathlib import Path
from functools import lru_cache
import json,hashlib,math
import numpy as np
import pandas as pd
DEFINITIONS_SHA256='f895f20e41d57ac8b03ef413b7d09a41a88203be61d95ed2af29a0024e97f7c2'
FIXTURES={kind:Path(__file__).with_name('fixtures')/name for kind,name in
    [('rout','rout_reference.json'),('report','outlier_report_reference.json')]}
@lru_cache(maxsize=1)
def _fixtures():return {key:json.loads(path.read_text(encoding='utf-8')) for key,path in FIXTURES.items()}
@lru_cache(maxsize=1)
def _rows():return {row['case']['key']:row for fixture in _fixtures().values() for row in fixture['rows']}
def cases():return json.loads(json.dumps([row['case'] for fixture in _fixtures().values() for row in fixture['rows']]))
def expected(case):return json.loads(json.dumps(_rows()[case['key']]['expected']))
def kind(case):return 'rout' if case['key'].startswith('rout-full.') else 'report'
def capability(case):return 'PyFLASH.stats_extra.'+('rout_outlier_stats' if kind(case)=='rout' else 'flag_outliers')
def clean(value):
    if isinstance(value,np.ndarray):return clean(value.tolist())
    if isinstance(value,(tuple,list)):return [clean(v) for v in value]
    if isinstance(value,float) and not math.isfinite(value):return None
    return value
def production(case):
    from PyFLASH.stats_extra import rout_outlier_stats,flag_outliers
    p=json.loads(json.dumps(case['parameters']))
    if kind(case)=='rout':return clean(rout_outlier_stats(p.pop('values'),**p))
    df=pd.DataFrame(case['input']['data'],index=case['input']['index']);groups=case['input']['groups']
    if case['column_form']=='tuple':p['columns']=tuple(p['columns'])
    if groups is None:labels=None
    elif case['group_form']=='positional':labels=list(groups)
    elif case['group_form']=='mapping':labels=dict(zip(df.index,groups))
    else:labels=pd.Series(groups,index=df.index)
    answer=flag_outliers(df,group_labels=labels,**p)
    return {'columns':list(answer.columns),'rows':clean(answer.astype(object).values.tolist())}
def component(a,b,atol=1e-12):
    if isinstance(a,list):return isinstance(b,list) and len(a)==len(b) and all(component(x,y,atol) for x,y in zip(a,b))
    if a is None or b is None:return a is b
    if isinstance(a,bool) or isinstance(b,bool):return a is b
    if isinstance(a,(float,int)) and isinstance(b,(float,int)):return math.isclose(a,b,rel_tol=1e-9,abs_tol=atol)
    return a==b
def equal(case,a,b):
    if kind(case)=='rout':return len(a)==len(b)==6 and all(component(x,y,0. if i in [1,2] else 1e-12) for i,(x,y) in enumerate(zip(a,b)))
    return (isinstance(a,dict) and isinstance(b,dict) and a.keys()==b.keys() and a['columns']==b['columns']
        and len(a['rows'])==len(b['rows']) and all(len(x)==len(y) and all(component(u,v,0. if i in [10,11] else 1e-12)
        for i,(u,v) in enumerate(zip(x,y))) for x,y in zip(a['rows'],b['rows'])))
def check_identity():
    fixtures=_fixtures();root=Path(__file__).parent
    if hashlib.sha256(json.dumps(cases(),sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()!=DEFINITIONS_SHA256:
        raise ValueError('Outlier frozen input definitions changed')
    for fixture in fixtures.values():
        if hashlib.sha256(Path(__file__).read_bytes()).hexdigest()!=fixture['adapter_sha256']:raise ValueError('Outlier reference adapter changed')
        for name,sha in {**fixture['source_manifest'],**fixture['mathematical_modules']}.items():
            if hashlib.sha256((root/name).read_bytes()).hexdigest()!=sha:raise ValueError('Outlier independent source changed')
    return fixtures
