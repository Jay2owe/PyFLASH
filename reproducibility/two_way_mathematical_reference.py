"""Independent exact hierarchical projections for complete two-factor reports."""
from fractions import Fraction as Q
import math
import mpmath as mp
from reproducibility.variance_student_mathematical_reference import number
from reproducibility.one_way_mathematical_reference import pairs,clean
from reproducibility.one_way_report_reference import annotation
import json
from pathlib import Path
inputs_data=json.loads((Path(__file__).parent/'reference-sources/two-way-reports/inputs/inputs.json').read_text())
RANGE=inputs_data['range_probabilities']

def finite(value):
    try:value=float(value)
    except (ValueError,TypeError,OverflowError):return None
    return Q(value) if math.isfinite(value) else None

def projection(values,columns):
    # Rational orthogonal projection never chooses rank using a float threshold.
    basis=[]
    for column in columns:
        vector=list(map(Q,column))
        for b in basis:
            scale=sum(x*y for x,y in zip(vector,b))/sum(x*x for x in b)
            vector=[x-scale*y for x,y in zip(vector,b)]
        if any(vector):basis.append(vector)
    fitted=sum((sum(y*b for y,b in zip(values,column))**2/sum(b*b for b in column) for column in basis),Q())
    return sum(y*y for y in values)-fitted,len(basis)

def cell_residual(values,levels):
    cells={}
    for y,key in zip(values,levels):cells.setdefault(key,[]).append(y)
    return sum((sum((v-sum(group)/len(group))**2 for v in group) for group in cells.values()),Q()),len(cells)

def f_probability(statistic,first,second):
    if statistic is None:return math.nan
    if statistic==math.inf:return 0.
    with mp.workdps(80):
        value=number(statistic);d=mp.mpf(second)
        return float(mp.betainc(d/2,mp.mpf(first)/2,0,d/(d+first*value),regularized=True))

def float_number(value):
    try:return float(value)
    except OverflowError:return math.inf if value>0 else -math.inf

def inputs(case):
    p=case['parameters'];column=p['column'];factors=p['factors']
    if factors is None:factors=case.get('default_factors',['FactorA','FactorB'])
    if not isinstance(column,str) or not column:raise ValueError('Named outcome required')
    if not isinstance(factors,(list,tuple)) or len(factors)!=2 or any(not isinstance(v,str) or not v for v in factors) or len(set(factors))!=2:raise ValueError('Exactly two named distinct factors required')
    names=case['conditions']
    if not isinstance(names,list) or any(not isinstance(v,str) or not v for v in names) or len(set(names))!=len(names):raise ValueError('Unique named conditions required')
    available=case.get('columns',list(case['frame'][0]) if case['frame'] else ['Condition','FactorA','FactorB','Marker'])
    if any(key not in available for key in ['Condition',column,*factors]):raise ValueError('Required column missing')
    tokens=p['comparisons']
    if tokens is None:tokens=[f'{first+1}-{first+gap+1}' for gap in range(1,len(names)) for first in range(len(names)-gap)]
    requested=pairs(tokens,len(names));retained=[]
    for row in case['frame']:
        value=finite(row.get(column));levels=[row.get(f) for f in factors]
        if row.get('Condition') not in names or value is None or any(v is None or isinstance(v,float) and not math.isfinite(v) for v in levels):continue
        if any(isinstance(v,(dict,list)) for v in levels):raise ValueError('Scalar category required')
        retained.append((row['Condition'],value,*levels))
    groups=[[row[1] for row in retained if row[0]==name] for name in names]
    return column,factors,names,requested,retained,groups

def geometry(retained):
    values=[r[1] for r in retained];a=[r[2] for r in retained];b=[r[3] for r in retained];n=len(values)
    levels_a=list(dict.fromkeys(a));levels_b=list(dict.fromkeys(b))
    additive=[[1]*n]+[[int(v==level) for v in a] for level in levels_a[1:]]+[[int(v==level) for v in b] for level in levels_b[1:]]
    sse_add,rank_add=projection(values,additive)
    sse_a,rank_a=cell_residual(values,a);sse_b,rank_b=cell_residual(values,b)
    sse_full,rank_full=cell_residual(values,list(zip(a,b)));df=n-rank_full
    sums=[sse_b-sse_add,sse_a-sse_add,sse_add-sse_full,sse_full]
    degrees=[rank_add-rank_b,rank_add-rank_a,rank_full-rank_add,df];statistics=[];probabilities=[]
    for ss,first in zip(sums[:3],degrees[:3]):
        if first<=0 or df<=0:statistic=None
        elif not sse_full:statistic=math.inf if ss else None
        else:statistic=ss*df/(sse_full*first)
        statistics.append(float_number(statistic) if statistic is not None else math.nan)
        probabilities.append(f_probability(statistic,first,df))
    return {'sums':[float_number(v) for v in sums],'p':probabilities+[math.nan],'f':statistics,'degrees':degrees}

def report(case):
    raw={} if case.get('empty_initial') else {'caller-note':'retained'}
    try:
        column,factors,names,requested,retained,groups=inputs(case)
        if len(groups)<2 or any(len(g)<2 for g in groups):
            return {'pvalues':[],'annotations':[],'overall':[[],[]],'results_dict':raw,'method':'Tukey','same_report_object':True}
        result=geometry(retained)
        raw['_group_test']={'symbol':'F','terms':[{'name':label,'statistic':stat,'p':prob,'df':[float(first),float(result['degrees'][-1])]} for label,stat,prob,first in zip([*factors,'Interaction'],result['f'],result['p'],result['degrees'])]}
        terms=[f'C({factors[0]})',f'C({factors[1]})',f'C({factors[0]}):C({factors[1]})','Residual']
        for term,ss,prob in zip(terms,result['sums'],result['p']):raw['2WA '+term.strip('C()')]=[ss,prob]
        statistics=[];probabilities=[];n=sum(map(len,groups));k=len(groups)
        means=[sum(g)/len(g) for g in groups];within=sum((sum((v-m)**2 for v in g) for g,m in zip(groups,means)),Q())
        for first,second in requested:
            difference=means[first]-means[second];uncertainty=within/Q(n-k)*(Q(1,len(groups[first]))+Q(1,len(groups[second])))
            statistics.append(float_number(difference))
            if not uncertainty:probability=0. if difference else math.nan
            else:
                a,b=sorted((first,second));probability=RANGE[f'two-way-range.{case["dataset"]}.{a}.{b}']
            probabilities.append(probability)
        raw['Tukey']=[statistics,probabilities];raw['Posthoc-Uncorrected']=[1,probabilities];raw['_audit_inputs']={'basis':'self_adjusted'}
        labels=[annotation(v,case['parameters']['ns']) for v in probabilities]
        if 'style' in case:
            style=case['style'];fallback=case['parameters']['ns']
            if fallback is None or fallback=='ns':fallback=style['significance_ns']
            labels=[]
            for probability in probabilities:
                label=round(probability,3) if fallback=='p' else fallback
                for threshold,symbol in sorted(style['significance_thresholds'].items(),key=lambda item:float(item[0])):
                    if probability<float(threshold):label=symbol;break
                labels.append(label)
        return clean({'pvalues':probabilities,'annotations':labels,
            'overall':[result['sums'],result['p']],'results_dict':raw,'method':'Tukey','same_report_object':True})
    except (ValueError,TypeError):return {'error':'ValueError'}
