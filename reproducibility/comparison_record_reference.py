"""Independent full literal report schema with exact group moments and ordering."""
from copy import deepcopy
import math
from reproducibility.group_description_reference import describe


def finite(value):
    try:number=float(value)
    except (TypeError,ValueError,OverflowError):return None
    return number if math.isfinite(number) else None


def coerce(value):
    if isinstance(value,dict):return {str(k):coerce(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [coerce(v) for v in value]
    if isinstance(value,float) and not math.isfinite(value):return None
    return value


def stars(p):
    if p is None:return 'ns'
    for level,annotation in ((.0001,'****'),(.001,'***'),(.01,'**'),(.05,'*')):
        if p<level:return annotation
    return 'ns'


def fmt(p):return 'n/a' if p is None else f'{p:.2e}' if p<.0001 else f'{p:.4g}'


def direction(groups):
    measured=[g for g in groups if g.get('mean') is not None]
    if len(measured)<2:return None
    if len(measured)==2:
        a,b=measured;symbol='≈' if a['mean']==b['mean'] else '>' if a['mean']>b['mean'] else '<'
        return f"{a['name']} {symbol} {b['name']}"
    low=min(g['mean'] for g in measured);high=max(g['mean'] for g in measured)
    if low==high:return f'all groups equal ({low:.4g})'
    lows=', '.join(g['name'] for g in measured if g['mean']==low);highs=', '.join(g['name'] for g in measured if g['mean']==high)
    return f'highest: {highs} ({high:.4g}); lowest: {lows} ({low:.4g})'


def report(case):
    p=deepcopy(case['parameters']);names=[str(n) if n is not None and str(n) else f'G{i+1}' for i,n in enumerate(p.get('group_names') or [])]
    values=p.get('group_values') or [];names+= [f'G{i+1}' for i in range(len(names),len(values))]
    groups=[describe({'name':names[i],'values':v}) for i,v in enumerate(values)]
    def text(value):return str(value) if value is not None and str(value) else None
    result={'kind':'group_comparison','metric':text(p.get('metric')) or 'metric','unit':'animal','n_groups':len(groups),'groups':groups,
        'test':{'name':text(p.get('test'))},'post_hoc':text(p.get('post_hoc')),'normal':None if p.get('normal') is None else bool(p['normal'])}
    if p.get('overall') is not None:
        stat,prob=p['overall'];labels=p.get('factor_terms') or []
        if isinstance(prob,(list,tuple)):
            stats=stat if isinstance(stat,(list,tuple)) else [stat]*len(prob)
            result['test']['terms']=[{'name':str(labels[i]) if i<len(labels) else f'term{i+1}','p':finite(pv),**({'statistic':finite(stats[i])} if i<len(stats) else {})} for i,pv in enumerate(prob)]
        else:result['test'].update(statistic=finite(stat),p=finite(prob))
    pairwise=[];prob=p.get('pairwise_pvalues');prob=[] if prob is None else prob if isinstance(prob,list) else [prob]
    for i,token in enumerate(p.get('comparisons') or []):
        a,b=map(int,token.split('-'));entry={'comparison':token}
        if 1<=a<=len(names):entry['a']=names[a-1]
        if 1<=b<=len(names):entry['b']=names[b-1]
        if i<len(prob):entry.update(p=finite(prob[i]),sig=stars(finite(prob[i])))
        pairwise.append(entry)
    result['pairwise']=pairwise;result['direction']=direction(groups)
    if p.get('effect_strings'):result['effect_sizes']=list(map(str,p['effect_strings']))
    if p.get('raw_stats') is not None:result['raw_stats']=coerce(p['raw_stats'])
    parts=[f"{result['metric']}: {result['test']['name'] or 'comparison'}"]
    terms=result['test'].get('terms')
    if terms:
        shown=[f"{term['name']} p={fmt(term['p'])} ({stars(term['p'])})" for term in terms if term['p'] is not None]
        if shown:parts.append('; '.join(shown))
    elif result['test'].get('p') is not None:
        pv=result['test']['p'];parts.append(f'p={fmt(pv)} ({stars(pv)})')
    if result['direction']:parts.append(result['direction'])
    result['headline']='; '.join(parts)
    return result
