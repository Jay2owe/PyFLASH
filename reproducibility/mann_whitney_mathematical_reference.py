"""Exact finite-sample rank distributions and 80-digit Gaussian rank tails."""
from fractions import Fraction
from math import comb,isfinite
import mpmath as mp
import re

def sample(values):
    if not isinstance(values,(list,tuple)):raise ValueError('One-dimensional real samples are required')
    result=[]
    for value in values:
        if isinstance(value,(list,tuple,dict,complex)):raise ValueError('One-dimensional real samples are required')
        try:v=float(value)
        except (TypeError,ValueError,OverflowError):continue
        if isfinite(v):result.append(Fraction(v))
    return result

def pairs(tokens,count):
    if not isinstance(tokens,(list,tuple)):raise ValueError('An ordered sequence of comparison pairs is required')
    result=[]
    for token in tokens:
        if not isinstance(token,str) or re.fullmatch(r'\s*[0-9]+\s*-\s*[0-9]+\s*',token) is None:raise ValueError('One-based comparison pairs are required')
        a,b=map(int,token.split('-'))
        if not 1<=a<=count or not 1<=b<=count or a==b:raise ValueError('Two distinct requested groups are required')
        result.append((a-1,b-1))
    return result

def inference(first,second):
    if not first or not second:return mp.nan,mp.nan
    n,m=len(first),len(second);data=first+second;size=n+m
    ranks={v:Fraction(2*sum(w<v for w in data)+sum(w==v for w in data)+1,2) for v in set(data)}
    u=sum(ranks[v] for v in first)-Fraction(n*(n+1),2)
    ties=[data.count(v) for v in set(data)]
    larger=max(u,n*m-u)
    if min(n,m)<=8 and max(ties)==1:
        # Independently count rank-sum subsets; no production distribution or
        # resampling implementation is used.
        counts=[{} for _ in range(n+1)];counts[0][0]=1
        for rank in range(1,size+1):
            for k in range(min(rank,n),0,-1):
                for total,weight in list(counts[k-1].items()):counts[k][total+rank]=counts[k].get(total+rank,0)+weight
        tail=sum(weight for total,weight in counts[n].items() if total-Fraction(n*(n+1),2)>=larger)
        probability=Fraction(min(2*tail,comb(size,n)),comb(size,n))
        return float(u),float(probability)
    variance=Fraction(n*m,12)*(size+1-Fraction(sum(t**3-t for t in ties),size*(size-1)))
    if variance==0:return float(u),1.
    with mp.workdps(80):
        number=lambda v:mp.mpf(v.numerator)/v.denominator
        z=number(larger-Fraction(n*m,2)-Fraction(1,2))/mp.sqrt(number(variance))
        probability=min(mp.mpf(1),mp.erfc(z/mp.sqrt(2)))
        return float(u),float(probability)

def clean(value):
    import math
    if isinstance(value,dict):return {k:clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [clean(v) for v in value]
    if isinstance(value,mp.mpf):value=float(value)
    return str(value) if isinstance(value,float) and not math.isfinite(value) else value

def reference(parameters):
    try:
        groups=list(map(sample,parameters['df_list']));requested=pairs(parameters['comparisons'],len(groups))
        numbers=[inference(groups[a],groups[b]) for a,b in requested]
        statistics=[v[0] for v in numbers];probabilities=[v[1] for v in numbers]
        labels=[];ns=parameters.get('ns','ns')
        for p in probabilities:
            label=round(float(p),3) if ns=='p' else ns
            for threshold,symbol in ((.0001,'****'),(.001,'***'),(.01,'**'),(.05,'*')):
                if p<threshold:label=symbol;break
            labels.append(label)
        raw={'caller-note':'retained','Mann-Whitney U':[statistics,probabilities],'_group_test':{'symbol':'U'},
             'Posthoc-Uncorrected':[1,probabilities],'_audit_inputs':{'basis':'raw'}}
        return clean({'pvalues':probabilities,'annotations':labels,'overall':[statistics,probabilities],'results_dict':raw,'method':'Mann-Whitney U'})
    except (ValueError,TypeError):return {'error':'ValueError'}
