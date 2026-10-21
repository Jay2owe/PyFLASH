"""Independent scalar probability/count domain and exact/high-precision answers."""
from fractions import Fraction
import math
import mpmath as mp

def mathematical(case):
    p=case['parameters'];probability=p['p_value'];count=p['n_tests']
    try:
        if case.get('probability_form')=='array1' or case.get('count_form')=='array1':raise ValueError('Scalar inputs required')
        if isinstance(probability,bool) or isinstance(count,bool):raise ValueError('Boolean inputs are not probabilities/counts')
        probability=float(probability)
        if not math.isfinite(probability) or not 0<=probability<=1:raise ValueError('Finite probability required')
        integer=int(count)
        if not isinstance(count,str) and count!=integer:raise ValueError('Whole count required')
        if integer<0:raise ValueError('Nonnegative count required')
        if not integer or not probability:return 0.
        if case['method']=='bonferroni_correction':return float(min(Fraction(probability)*integer,Fraction(1)))
        if probability==1:return 1.
        with mp.workdps(80):return float(-mp.expm1(mp.mpf(integer)*mp.log1p(-mp.mpf(probability))))
    except (ValueError,TypeError,OverflowError):return {'error':'ValueError'}
