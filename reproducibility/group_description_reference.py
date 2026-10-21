"""Independent exact moments and type-seven empirical quantiles for group reports."""
from fractions import Fraction as Q
import math
import mpmath as mp


def describe(case):
    raw=case['values'];values=[]
    for value in raw or []:
        try:number=float(value)
        except (TypeError,ValueError,OverflowError):continue
        if math.isfinite(number):values.append(Q(number))
    result={'name':str(case['name']) if case['name'] is not None and str(case['name']) else 'group','n':len(values)}
    if not values:return result
    values.sort();n=len(values);mean=sum(values)/n
    variance=sum((v-mean)**2 for v in values)/(n-1) if n>1 else Q(0)
    with mp.workdps(80):
        sd=float(mp.sqrt(mp.mpf(variance.numerator)/variance.denominator))
        sem=float(mp.sqrt(mp.mpf(variance.numerator)/(variance.denominator*n)))
    def quantile(fraction):
        at=(n-1)*fraction;lo=at.numerator//at.denominator;amount=at-lo
        return float(values[lo]*(1-amount)+values[min(lo+1,n-1)]*amount)
    result.update(mean=float(mean),sd=sd,sem=sem,median=quantile(Q(1,2)),min=float(values[0]),max=float(values[-1]),q25=quantile(Q(1,4)),q75=quantile(Q(3,4)))
    return result


def same(a,b):
    if isinstance(b,dict):return isinstance(a,dict) and a.keys()==b.keys() and all(same(a[k],b[k]) for k in b)
    if isinstance(b,(float,int)) and isinstance(a,(float,int)):return math.isclose(a,b,rel_tol=1e-9,abs_tol=0.)
    return type(a)==type(b) and a==b
