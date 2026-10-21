"""Independent rational OLS/sandwich equations and 80-digit inference."""
from fractions import Fraction as Q
from copy import deepcopy
import math
import mpmath as mp
from reproducibility.one_way_mathematical_reference import pairs, clean
from reproducibility.one_way_report_reference import adjusted, annotation, LABELS
from reproducibility.rank_report_reference import correction

def transpose(a): return list(map(list, zip(*a)))
def multiply(a,b): return [[sum((x*y for x,y in zip(row,col)),Q()) for col in transpose(b)] for row in a]
def inverse(a):
    n=len(a); rows=[list(row)+[Q(i==j) for j in range(n)] for i,row in enumerate(a)]
    for i in range(n):
        pivot=next((j for j in range(i,n) if rows[j][i]),None)
        if pivot is None:raise ValueError('Unidentifiable matrix')
        rows[i],rows[pivot]=rows[pivot],rows[i]
        divisor=rows[i][i];rows[i]=[v/divisor for v in rows[i]]
        for j in range(n):
            if j!=i:
                factor=rows[j][i];rows[j]=[a-factor*b for a,b in zip(rows[j],rows[i])]
    return [row[n:] for row in rows]
def pinverse(a):
    # Independent exact column-rank factorisation, without numerical rank cutoffs.
    basis={};columns=[]
    for j,column in enumerate(transpose(a)):
        reduced=list(column)
        for pivot,row in sorted(basis.items()):
            factor=reduced[pivot];reduced=[x-factor*y for x,y in zip(reduced,row)]
        pivot=next((i for i,x in enumerate(reduced) if x),None)
        if pivot is not None:
            divisor=reduced[pivot];basis[pivot]=[v/divisor for v in reduced];columns.append(j)
    rank=len(columns)
    if not rank:return [[Q()]*len(a) for _ in a[0]],0
    C=[[row[j] for j in columns] for row in a];Ct=transpose(C)
    left=multiply(inverse(multiply(Ct,C)),Ct);R=multiply(left,a);Rt=transpose(R)
    return multiply(multiply(Rt,inverse(multiply(R,Rt))),left),rank
def add(a,b): return [[x+y for x,y in zip(r,s)] for r,s in zip(a,b)]
def scale(a,value): return [[x*value for x in row] for row in a]
def outer(v): return [[a*b for b in v] for a in v]
def meat(scores):
    p=len(scores[0]);out=[[Q()]*p for _ in range(p)]
    for row in scores:out=add(out,outer(row))
    return out
def aggregate(scores,labels):
    grouped={}
    for row,label in zip(scores,labels):
        key=tuple(label) if isinstance(label,list) else label
        grouped[key]=[a+b for a,b in zip(grouped.get(key,[Q()]*len(row)),row)]
    return [grouped[key] for key in sorted(grouped)]
def hac(scores,lags,kernel,segments=None):
    out=meat(scores);segments=segments or [(0,len(scores))]
    for lag in range(1,lags+1):
        weight=Q(1) if kernel=='uniform' else Q(lags+1-lag,lags+1)
        for start,end in segments:
            for i in range(start+lag,end):
                cross=[[a*b for b in scores[i-lag]] for a in scores[i]]
                out=add(out,scale(add(cross,transpose(cross)),weight))
    return out
def number(v):return mp.mpf(v.numerator)/v.denominator
def probability(kind,statistic,df=None):
    with mp.workdps(80):
        x=number(statistic)
        if kind=='normal':return float(mp.erfc(mp.sqrt(x/2)))
        if kind=='t':
            d=mp.mpf(df);return float(mp.betainc(d/2,mp.mpf('.5'),0,d/(d+x),regularized=True))
        if x<=0:return 1.
        if kind=='chi':return float(mp.gammainc(mp.mpf(df)/2,x/2,mp.inf,regularized=True))
        numerator,denominator=df
        return float(mp.betainc(mp.mpf(denominator)/2,mp.mpf(numerator)/2,0,denominator/(denominator+numerator*x),regularized=True))
def finite(value):
    try:return not isinstance(value,bool) and math.isfinite(float(value))
    except (ValueError,TypeError):return False

def named_list(value):
    if value is None:return []
    return [value] if isinstance(value,str) else list(value)

def fit(case):
    parameters=case['parameters'];data=case['data'];order=parameters.get('group_order')
    group=parameters['group_col'];outcome=parameters['outcome_col']
    if order is None:order=list(dict.fromkeys(str(v) for v in data[group] if v is not None))
    if len(set(order))!=len(order):raise ValueError('Duplicate group order')
    wanted=pairs(parameters['comparisons'],len(order))
    covariates=named_list(parameters.get('covariates'))
    categorical=named_list(parameters.get('categorical_covariates'))
    if len(set(covariates))!=len(covariates) or not set(categorical)<=set(covariates):raise ValueError('Invalid covariate declarations')
    numeric=[name for name in covariates if name not in categorical]
    ids=[i for i,v in enumerate(data[outcome]) if finite(v) and data[group][i] is not None and str(data[group][i]) in order
         and all(finite(data[c][i]) for c in numeric) and all(data[c][i] is not None for c in categorical)]
    if len(order)<2 or any(sum(str(data[group][i])==g for i in ids)<2 for g in order):return None,order,wanted
    levels={c:sorted(set(str(data[c][i]) for i in ids)) for c in categorical}
    X=[]
    for i in ids:
        row=[Q(1)]+[Q(str(data[group][i])==g) for g in order[1:]]
        for c in covariates:
            row.extend(Q(str(data[c][i])==level) for level in levels[c][1:]) if c in categorical else row.append(Q(float(data[c][i])))
        X.append(row)
    y=[[Q(float(data[outcome][i]))] for i in ids];n=len(X);p=len(X[0]);bread=inverse(multiply(transpose(X),X))
    beta=multiply(multiply(bread,transpose(X)),y);pred=multiply(X,beta);errors=[a[0]-b[0] for a,b in zip(y,pred)]
    df=n-p;cov_type=parameters.get('cov_type','HC3');kw=deepcopy(parameters.get('cov_kwds') or {});kind=(cov_type or 'nonrobust').lower()
    if df<=0:raise ValueError('No residual degrees of freedom')
    if kind not in ('nonrobust','fixed scale','fixed_scale','hc0','hc1','hc2','hc3','hac','cluster','hac-panel','hac-groupsum'):raise ValueError('Unknown covariance')
    if kind in ('hc0','hc1','hc2','hc3') and set(kw)-{'use_t'}:raise ValueError('Unsupported HC keyword')
    if 'use_t' in kw and kw['use_t'] is not None and not isinstance(kw['use_t'],bool):raise ValueError('Invalid inference option')
    use_t=kw.get('use_t',kind=='nonrobust');df_inference=df
    scores=[[v*e for v in row] for row,e in zip(X,errors)]
    if kind=='nonrobust':cov=scale(bread,sum((e*e for e in errors),Q())/df)
    elif kind in ('fixed scale','fixed_scale'):cov=scale(bread,Q(kw.get('scale',1)))
    else:
        if kind in ('hc0','hc1','hc2','hc3'):
            m=[[Q()]*p for _ in range(p)]
            for row,e in zip(X,errors):
                h=multiply(multiply([row],bread),transpose([row]))[0][0]
                factor=Q(n,df) if kind=='hc1' else (1-h)**(-int(kind[-1])+1) if kind in ('hc2','hc3') else Q(1)
                m=add(m,scale(outer(row),e*e*factor))
        elif kind=='hac':
            m=hac(scores,kw['maxlags'],kw.get('kernel',kw.get('weights_func','bartlett')))
            if kw.get('use_correction',False):m=scale(m,Q(n,df))
        elif kind=='cluster':
            labels=[kw['groups'][i] for i in ids];two=isinstance(labels[0],list)
            def clustered(labels):
                groups=aggregate(scores,labels);count=len(groups);m=meat(groups)
                return scale(m,Q(count,count-1)*Q(n-1,df)) if kw.get('use_correction',True) else m
            if two:
                first=[v[0] for v in labels];second=[v[1] for v in labels]
                m=add(add(clustered(first),clustered(second)),scale(clustered(labels),Q(-1)));count=min(len(set(first)),len(set(second)))
            else:m=clustered(labels);count=len(set(labels))
            if kw.get('df_correction',True) is not False:df_inference=count-1
        elif kind in ('hac-panel','hac-groupsum'):
            times=[kw['time'][i] for i in ids] if 'time' in kw else None
            if kind=='hac-panel':
                labels=[kw['groups'][i] for i in ids] if 'groups' in kw else None
                cuts=[0]+[i for i in range(1,n) if (labels[i]!=labels[i-1] if labels is not None else times[i]<times[i-1])]+[n]
                segments=list(zip(cuts,cuts[1:]));count=len(segments)
                m=hac(scores,kw['maxlags'],kw.get('kernel',kw.get('weights_func','bartlett')),segments)
                correction_kind=kw.get('use_correction','hac');correction_count=count
            else:
                sums=aggregate(scores,times);m=hac(sums,kw['maxlags'],kw.get('kernel',kw.get('weights_func','bartlett')))
                count=1+sum(times[i]<times[i-1] for i in range(1,n));correction_count=len(set(times));correction_kind=kw.get('use_correction','cluster')
            if correction_kind=='hac':m=scale(m,Q(n,df))
            elif correction_kind in ('c','clu','cluster'):m=scale(m,Q(correction_count,correction_count-1)*Q(n-1,df))
            if kw.get('df_correction',True) is not False:df_inference=count-1
        else:raise ValueError('Unknown covariance')
        cov=multiply(multiply(bread,m),bread)
    return {'beta':beta,'cov':cov,'use_t':use_t,'df':df_inference,'order':order},order,wanted

def report(case):
    p=case['parameters'];raw={'caller-note':'retained'}
    try:
        model,order,requested=fit(case);method=correction(p.get('posthoc_correction','auto'),len(requested))
        if model is None:return {'pvalues':[],'annotations':[],'overall':['nan','nan'],'results_dict':raw,'method':'model contrasts'}
        beta,cov,use_t,df=model['beta'],model['cov'],model['use_t'],model['df'];k=len(order)-1
        b=beta[1:1+k];v=[row[1:1+k] for row in cov[1:1+k]]
        vinv,rank=pinverse(v);wald=multiply(multiply(transpose(b),vinv),b)[0][0]
        overall=wald/rank if use_t and rank else math.nan if use_t else wald
        overall_p=probability('f' if use_t else 'chi',overall,(rank,df) if use_t else rank) if rank else math.nan
        raw['_group_test']={'symbol':'F' if use_t else 'chi2','df':[float(rank),float(df)] if use_t else [float(rank)]}
        raw['Linear Model']=[float(overall),overall_p]
        statistics=[];probabilities=[]
        for a,b in requested:
            c=[Q()]*len(beta)
            if b:c[b]+=1
            if a:c[a]-=1
            estimate=multiply([c],beta)[0][0];variance=multiply(multiply([c],cov),transpose([c]))[0][0]
            if variance<=0:statistic=prob=math.nan
            else:
                squared=estimate**2/variance;statistic=math.copysign(math.sqrt(float(squared)),float(estimate))
                prob=probability('t' if use_t else 'normal',squared,df)
            statistics.append(statistic);probabilities.append(prob)
        if method=='westfall_young':
            from reproducibility.audit_parent_reference import NO_NULL
            raw['Correction-Unavailable']=[NO_NULL,math.nan];method=correction('auto',len(requested))
        label=LABELS[method];values=adjusted(probabilities,method)
        raw['_audit_inputs']={'correction':label,'basis':'raw'}
        raw['Linear-Model-Contrasts-Uncorrected']=[statistics,probabilities];raw['Posthoc-Uncorrected']=[1,probabilities]
        raw['Linear-Model-Contrasts-'+label]=[statistics,values]
        return clean({'pvalues':values,'annotations':[annotation(v,p['ns']) for v in values],
            'overall':[float(overall),overall_p],'results_dict':raw,'method':('model contrasts'+(' '+str(p.get('cov_type','HC3')) if p.get('cov_type','HC3') else '')+' '+label).strip()})
    except (ValueError,KeyError,TypeError,ZeroDivisionError):return {'error':'ValueError'}
