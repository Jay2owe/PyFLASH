"""Literal complete record schemas; numbers are supplied inputs, not fitted here."""
import math
from copy import deepcopy


def number(value,integer=False):
    try:
        result=int(value) if integer else float(value)
        return result if integer or math.isfinite(result) else None
    except (TypeError,ValueError,OverflowError):return None


def label(value):return None if value is None or str(value)=='' else str(value)


def labels(value):
    return [label(item) for item in ([value] if isinstance(value,str) else [] if value is None else list(value))]


def clean(value):
    if isinstance(value,dict):return {str(key):clean(item) for key,item in value.items()}
    if isinstance(value,(list,tuple)):return [clean(item) for item in value]
    if isinstance(value,float) and not math.isfinite(value):return None
    return value


def stars(value):
    value=number(value)
    if value is None:return 'ns'
    for threshold,text in ((.0001,'****'),(.001,'***'),(.01,'**'),(.05,'*')):
        if value<threshold:return text
    return 'ns'


def probability(value):
    value=number(value)
    return 'n/a' if value is None else f'{value:.2e}' if value<.0001 else f'{value:.4g}'


def report(case):
    p=case['parameters'];kind=case['kind']
    if kind=='stars':return stars(p['p'])
    if kind=='correlation':
        out={'kind':kind,**{key:label(p.get(key)) for key in ('x','y','group','method')},
             'n':number(p.get('n'),True),'r':number(p.get('r')),'p':number(p.get('p'))}
        group=f" [{out['group']}]" if out['group'] else ''
        coefficient=f"r={out['r']:.3g}" if out['r'] is not None else 'r=n/a'
        tail=f"; p={probability(out['p'])} ({stars(out['p'])})" if out['p'] is not None else ''
        out['headline']=f"{out['y']} vs {out['x']}{group}: {coefficient}{tail}"
        return out
    if kind=='multivariable_regression':
        out={'kind':kind,**{key:label(p.get(key)) for key in ('predictor_set','y','group')},
            'predictors':labels(p.get('predictors')),**{key:number(p.get(key),key in ('n','df_model','df_resid')) for key in ('n','r2','adj_r2','f','p','q','df_model','df_resid')},
            'coefficients':{str(key):number(value) for key,value in p.get('coefficients',{}).items()} if isinstance(p.get('coefficients'),dict) else {},
            'rank_deficient':bool(p['rank_deficient']) if p.get('rank_deficient') is not None else None}
        predictor=out['predictor_set'] or ' + '.join(item for item in out['predictors'] if item) or 'predictors'
        group=f" [{out['group']}]" if out['group'] else ''
        coefficient=f"R2={out['r2']:.3g}" if out['r2'] is not None else 'R2=n/a'
        tail='; '.join(f'{key}={probability(out[key])}' for key in ('p','q') if out[key] is not None)
        out['headline']=f"{out['y'] or 'y'} ~ {predictor}{group}: {coefficient}"+(f'; {tail}' if tail else '')
        return out
    assert kind=='linear_model'
    out={'kind':kind,**{key:label(p.get(key)) for key in ('dependent_variable','formula','group')},
        'predictors':labels(p.get('predictors')),'covariates':labels(p.get('covariates')),
        **{key:number(p.get(key),key=='n') for key in ('n','r2','adj_r2','f','p')},
        **{key:clean(p[key]) if isinstance(p.get(key),dict) else {} for key in ('coefficients','adjusted_means')}}
    if p.get('component_models') is not None:out['component_models']=clean(p['component_models'])
    group=f" by {out['group']}" if out['group'] else ''
    coefficient=(f"adjusted R2={out['adj_r2']:.3g}" if out['adj_r2'] is not None else f"R2={out['r2']:.3g}" if out['r2'] is not None else 'R2=n/a')
    tail=f"; model p={probability(out['p'])}" if out['p'] is not None else ''
    out['headline']=f"{out['dependent_variable'] or 'dependent variable'}{group}: {coefficient}{tail}"
    return out
