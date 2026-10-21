"""Preserve exact geometry until dimensionless inference and output rounding."""
import numpy as np

def _power_of_two_scale(*arrays):
    """Preserve shapes and ratios while keeping finite moments representable."""
    largest = max((float(np.max(np.abs(a))) for a in arrays if a.size), default=0.)
    if not np.isfinite(largest) or largest == 0:
        return arrays
    exponent = int(np.frexp(largest)[1])
    return tuple(np.ldexp(a, -exponent) for a in arrays)


"""Keep exact contrasts through scaling before rounding returned float fields."""
import math
from fractions import Fraction

def _rational_float(value):
    try:return float(value)
    except OverflowError:return math.inf if value>0 else -math.inf

def _rational_sqrt(value):
    if not value:return 0.
    if value<0:return math.nan
    value=Fraction(value)
    exponent=value.numerator.bit_length()-value.denominator.bit_length()
    exponent-=exponent%2
    scaled=value/(1<<exponent) if exponent>=0 else value*(1<<(-exponent))
    try:return math.ldexp(math.sqrt(float(scaled)),exponent//2)
    except OverflowError:return math.inf

def _rational_log(value):
    value=Fraction(value)
    return math.log(value.numerator)-math.log(value.denominator)

def _f_tail_ratio(squared,first,degrees):
    from scipy.stats import f
    from scipy.special import betainc,betaln
    statistic=_rational_float(squared)
    probability=float(f.sf(statistic,first,float(degrees)))
    if probability>0 or math.isnan(statistic) or squared==math.inf:return probability
    ratio=Fraction(degrees)/(Fraction(degrees)+first*squared)
    x=_rational_float(ratio);a,b=float(degrees)/2,first/2
    if x<2.2250738585072014e-308:
        return math.exp(a*_rational_log(ratio)-math.log(a)-float(betaln(a,b)))
    answer=float(betainc(a,b,x))
    if answer>0:return answer
    # The ratio in this branch is far below machine epsilon. The next beta
    # series term is smaller than 1e-300 relative, while taking its logarithm
    # before casting preserves a representable probability below its squared t.
    if x<1e-8:
        return math.exp(a*_rational_log(ratio)-math.log(a)-float(betaln(a,b)))
    return answer

def _t_tail_squared(squared,degrees):
    from scipy.stats import t
    statistic=_rational_sqrt(squared)
    probability=float(2*t.sf(statistic,float(degrees)))
    if probability>0 and _rational_float(squared)!=math.inf:return probability
    return _f_tail_ratio(squared,1,degrees)

