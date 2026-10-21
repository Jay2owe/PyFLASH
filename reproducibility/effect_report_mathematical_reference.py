"""Independent complete report composition; no extra child or RNG vote."""
import json, hashlib, math
import numpy as np
from reproducibility.scalar_contracts import reference as scalar
from reproducibility.bootstrap_reference import interval
from reproducibility.effect_magnitude_contract import reference as magnitude, BANDS
parametric = {"Independent T-Test", "Student's T-Test", "Welch's T-Test",
              "One-Way ANOVA", "Welch ANOVA", "Two-Way ANOVA"}
draws_cache = {}
interval_cache = {}
labels = {v:k for k,v in BANDS.items()}
def finite_groups(raw):
    result=[]
    for group in raw:
        clean=[]
        for value in group:
            try:value=float(value)
            except (ValueError,TypeError):continue
            if math.isfinite(value):clean.append(value)
        result.append(clean)
    return result

def packed(value):
    if isinstance(value,dict):return {k:packed(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [packed(v) for v in value]
    return None if isinstance(value,float) and not math.isfinite(value) else value

def equal(a,b):
    if isinstance(a,dict):return isinstance(b,dict) and a.keys()==b.keys() and all(equal(a[k],b[k]) for k in a)
    if isinstance(a,list):return isinstance(b,list) and len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
    if a is None or b is None:return a is b
    if isinstance(a,(float,int)) and isinstance(b,(float,int)):return math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-12)
    return a==b

def generator(case,production=False):
    if case['rng_kind']=='generator':return np.random.default_rng(case['seed'])
    if case['rng_kind']=='random-state':return np.random.RandomState(case['seed'])
    return case['seed'] if production else np.random.RandomState(case['seed'])

def reference(case):
    p=case['parameters'];groups=finite_groups(p['groups']);test=p['test']
    answer={'overall':{},'pairwise':[],'family':None};arrangements=[]
    if test=='Linear Model':return answer,arrangements
    if test=='One-Way ANOVA':
        values=scalar({'capability':'PyFLASH.stats_extra.anova_effect_sizes','parameters':{'groups':groups}})
        answer['overall']=dict(zip(['eta_squared','omega_squared'],values));answer['family']='omega_squared'
    elif test=='Kruskal-Wallis':
        answer['overall']={'epsilon_squared':scalar({'capability':'PyFLASH.stats_extra.kw_epsilon_squared','parameters':{'groups':groups}})[0]}
        answer['family']='epsilon_squared'
    shared=generator(case)
    for number,token in enumerate(p['comparisons']):
        i,j=[int(v)-1 for v in token.split('-')];a,b=groups[i],groups[j]
        name='hedges_g' if test in parametric else 'rank_biserial'
        value=scalar({'capability':'PyFLASH.stats_extra.'+name,'parameters':{'a':a,'b':b}})[0]
        endpoints=[None,None]
        if p['ci'] and test in parametric and min(len(a),len(b))>=2:
            rng=shared if case['rng_kind'] in ['generator','random-state'] else generator(case)
            state=rng.bit_generator.state if case['rng_kind']=='generator' else [rng.get_state()[0],rng.get_state()[1].tolist(),*rng.get_state()[2:]]
            identity=json.dumps({'samples':[a,b],'count':p['n_resamples'],'state':state},sort_keys=True)
            key=hashlib.sha256(identity.encode('utf-8')).hexdigest()
            method=rng.integers if case['rng_kind']=='generator' else rng.randint
            draws=[method(0,len(sample),size=(p['n_resamples'],len(sample))).tolist() for sample in [a,b]]
            if key not in draws_cache:
                draws_cache[key]={'key':key,'inputs':[a,b],'n_resamples':p['n_resamples'],'draws':draws,'generator_state_before':state}
                try:interval_cache[key]=packed(interval(a,b,'hedges',.95,draws))
                except (ValueError,ZeroDivisionError,OverflowError):interval_cache[key]=[None,None]
                draws_cache[key]['independent_endpoints']=interval_cache[key]
            endpoints=interval_cache[key];arrangements.append({'comparison_position':number,'draw_key':key})
        kind='d' if test in parametric else 'r';band=magnitude({'parameters':{'value':value,'kind':kind}})[0]
        answer['pairwise'].append({'comparison':token,'metric':'hedges_g' if test in parametric else 'rank_biserial_r',
            'value':value,'ci_low':endpoints[0],'ci_high':endpoints[1],'interpretation':labels[band]})
    return packed(answer),arrangements
