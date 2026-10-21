"""Independent exact-measurement effects and the two-sample BCa equations."""
from fractions import Fraction as Q
from statistics import NormalDist
import math
import mpmath as mp


def effect(a,b,kind):
    if min(len(a),len(b))<2:return math.nan
    a,b=[list(map(Q,group)) for group in (a,b)];ma,mb=sum(a)/len(a),sum(b)/len(b)
    variance=(sum((value-ma)**2 for value in a)+sum((value-mb)**2 for value in b))/(len(a)+len(b)-2)
    if not variance:return math.nan
    with mp.workdps(80):
        difference=ma-mb
        value=(mp.mpf(difference.numerator)/difference.denominator)/mp.sqrt(mp.mpf(variance.numerator)/variance.denominator)
        if kind=='hedges':value*=1-mp.mpf(3)/(4*(len(a)+len(b))-9)
        return float(value)


def interval(a,b,kind,confidence,draws):
    try:
        distribution=[effect([a[i] for i in ix],[b[i] for i in iy],kind) for ix,iy in zip(*draws)]
        estimate=effect(a,b,kind)
        if not math.isfinite(estimate) or any(not math.isfinite(v) for v in distribution):return ['nan','nan']
        distribution.sort();normal=NormalDist()
        percentile=(sum(value<estimate for value in distribution)+sum(value<=estimate for value in distribution))/(2*len(distribution))
        z0=normal.inv_cdf(percentile);cubes=[];squares=[]
        for group in (0,1):
            sample=(a,b)[group]
            jackknife=[effect(a[:i]+a[i+1:],b,kind) if group==0 else effect(a,b[:i]+b[i+1:],kind) for i in range(len(sample))]
            if any(not math.isfinite(value) for value in jackknife):return ['nan','nan']
            center=math.fsum(jackknife)/len(sample);influence=[(len(sample)-1)*(center-value) for value in jackknife]
            cubes.append(math.fsum(value**3 for value in influence)/len(sample)**3)
            squares.append(math.fsum(value**2 for value in influence)/len(sample)**2)
        acceleration=math.fsum(cubes)/(6*math.fsum(squares)**1.5)
        def quantile(probability):
            position=probability*(len(distribution)-1);index=int(position);weight=position-index
            return distribution[index]*(1-weight)+distribution[min(index+1,len(distribution)-1)]*weight
        result=[]
        for tail in ((1-confidence)/2,(1+confidence)/2):
            z=normal.inv_cdf(tail);p=normal.cdf(z0+(z0+z)/(1-acceleration*(z0+z)));result.append(quantile(p))
        return result if all(math.isfinite(value) for value in result) else ['nan','nan']
    except (ValueError,ZeroDivisionError,OverflowError):return ['nan','nan']
