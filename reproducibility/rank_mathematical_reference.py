"""Independent rational midranks and 80-digit rank inference, no app imports."""
from collections import Counter
from fractions import Fraction as Q
from functools import lru_cache
import math
import mpmath as mp
from reproducibility.variance_student_mathematical_reference import sample,number

def ranks(values):
    counts=Counter(values);lookup={};position=1
    for value,count in sorted(counts.items()):
        lookup[value]=Q(2*position+count-1,2);position+=count
    return [lookup[v] for v in values]

@lru_cache(maxsize=4096)
def tail(kind,squared,df):
    with mp.workdps(80):
        x=number(squared)
        if kind=='normal':return float(mp.erfc(mp.sqrt(x/2)))
        if kind=='t':
            d=number(df);return float(mp.betainc(d/2,mp.mpf('.5'),0,d/(d+x),regularized=True))
        return float(mp.gammainc(mp.mpf(df)/2,x/2,mp.inf,regularized=True))

def geometry(groups):
    sizes=list(map(len,groups));n=sum(sizes);k=len(groups)
    if k<2 or not all(sizes):return {'identified':False}
    pooled=[v for g in groups for v in g];ranked=ranks(pooled)
    cuts=[sum(sizes[:i]) for i in range(k+1)]
    means=[sum(ranked[cuts[i]:cuts[i+1]],Q())/sizes[i] for i in range(k)]
    ties=sum(c**3-c for c in Counter(pooled).values())
    variance=Q(n*(n+1),12)-Q(ties,12*(n-1))
    correction=1-Q(ties,n**3-n)
    h=(Q(12,n*(n+1))*sum(s*m*m for s,m in zip(sizes,means))-3*(n+1))/correction if correction else None
    return {'identified':True,'sizes':sizes,'n':n,'k':k,'ranks':ranked,'means':means,
            'variance':variance,'h_exact':h,'h':float(h) if h is not None else math.nan,
            'p':tail('chi',h,k-1) if h is not None else math.nan}

def pair(design,groups,first,second,kind):
    sizes=design['sizes'];n,k=design['n'],design['k'];delta=design['means'][first]-design['means'][second]
    variance=design['variance']*(Q(1,sizes[first])+Q(1,sizes[second]))
    if kind=='DSCF':
        a,b=groups[first],groups[second];ni,nj=len(a),len(b);s=ni+nj
        ranked=ranks(a+b);tied=sum(c**3-c for c in Counter(a+b).values())
        u=sum(ranked[:ni],Q())-Q(ni*(ni+1),2)
        variance=Q(ni*nj,s*(s-1))*Q(s**3-s-tied,12)
        squared=2*(u-Q(ni*nj,2))**2/variance if variance else None
        return (math.sqrt(float(squared)),None,squared) if squared is not None else (math.nan,math.nan,None)
    if kind=='Conover':
        if n==k or design['h_exact'] is None:return math.nan,math.nan,None
        variance*=Q(n-1)-design['h_exact'];variance/=n-k
    if not variance:
        if delta and kind=='Conover':return math.copysign(math.inf,float(delta)),0.,None
        return math.nan,math.nan,None
    squared=delta**2/variance
    if kind=='Nemenyi':return float(squared),tail('chi',squared,k-1),squared
    statistic=math.sqrt(float(squared))
    if kind=='Conover':statistic=math.copysign(statistic,float(delta))
    return statistic,tail('t' if kind=='Conover' else 'normal',squared,n-k),squared
