"""Unchanged exact-rational growth benchmark frozen before correction."""
from fractions import Fraction
import math
import mpmath as mp

def reference(case):
    p=case['parameters'];pairs=[(Fraction(float(x)),Fraction(float(y))) for x,y in zip(p['x'],p['y'])
        if x is not None and y is not None and math.isfinite(float(x)) and math.isfinite(float(y))]
    n=len(pairs);sx=sum(x for x,y in pairs);sy=sum(y for x,y in pairs);sxx=sum(x*x for x,y in pairs);sxy=sum(x*y for x,y in pairs)
    denominator=n*sxx-sx*sx;slope=(n*sxy-sx*sy)/denominator;intercept=(sy-slope*sx)/n
    sse=sum((y-slope*x-intercept)**2 for x,y in pairs);sst=sum((y-sy/n)**2 for x,y in pairs)
    with mp.workdps(70):
        high=lambda value:mp.mpf(value.numerator)/value.denominator
        residual=high(sse)/(n-2)
        stderr=[float(mp.sqrt(residual*high(Fraction(n,1)/denominator))),float(mp.sqrt(residual*high(sxx/denominator)))]
        aic=float(n*mp.log(high(sse)/n)+4) if sse else '-inf'
        r2=float(1-sse/sst) if sst else 'nan'
    return {'model':'linear','params':{'slope':{'value':float(slope),'stderr':stderr[0]},
        'intercept':{'value':float(intercept),'stderr':stderr[1]}},'r_squared':r2,'aic':aic,'n':n,
        'predictions':[float(slope*Fraction(float(x))+intercept) for x in p['prediction_x']],
        'all_models':{'linear':{'aic':aic}}}
