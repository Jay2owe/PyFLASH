"""Stable upper events for the studentized Gaussian range."""
import math
from functools import lru_cache
import numpy as np
from scipy.integrate import quad
from scipy.special import log_ndtr,gammaln,roots_hermitenorm
from scipy.stats import t,studentized_range

_NORMAL_RULES=[(nodes,weights/math.sqrt(2*math.pi)) for nodes,weights in
               [roots_hermitenorm(order) for order in (32,64,128,256)]]

def _normal_range_tail(width,count):
    if width==0:return 1.
    if math.isinf(width):return 0.
    previous=None
    for nodes,weights in _NORMAL_RULES:
        base=log_ndtr(-nodes);other=log_ndtr(-(nodes+width))
        ratios=np.minimum(1.,np.exp(other-base))
        with np.errstate(divide='ignore',invalid='ignore'):
            outside=np.exp((count-1)*base)*(-np.expm1((count-1)*np.log1p(-ratios)))
        answer=float(count*(weights@outside))
        if previous is not None and answer>0 and abs(answer-previous)<=2e-12*answer:return answer
        previous=answer
    def integrand(offset):
        z=offset-width/2
        base=float(log_ndtr(-z));other=float(log_ndtr(-(z+width)))
        ratio=min(1.,math.exp(other-base))
        union=1. if ratio==1 else -math.expm1((count-1)*math.log1p(-ratio))
        return count*math.exp(-z*z/2+(count-1)*base)*union/math.sqrt(2*math.pi)
    return quad(integrand,-math.inf,math.inf,epsabs=0,epsrel=2e-12,limit=200)[0]

@lru_cache(maxsize=256)
def range_tail(threshold,count,degrees):
    if threshold<=0:return 1.
    if threshold==math.inf:return 0.
    if math.isnan(threshold) or math.isnan(degrees):return math.nan
    if count==2:return float(2*t.sf(threshold/math.sqrt(2),degrees))
    probability=float(studentized_range.sf(threshold,count,degrees))
    if probability>=1e-6:return probability
    if degrees==math.inf:return _normal_range_tail(threshold,count)
    constant=math.log(2)+(degrees/2)*math.log(degrees/2)-float(gammaln(degrees/2))
    stretch=max(1.,threshold/math.sqrt(degrees))
    def radial(position):
        scale=position/stretch
        if scale<=0:return 0.
        density=math.exp(constant+(degrees-1)*math.log(scale)-degrees*scale*scale/2)/stretch
        if density==0:return 0.
        return _normal_range_tail(threshold*scale,count)*density
    return quad(radial,0,math.inf,epsabs=0,epsrel=2e-11,limit=200)[0]


"""Preserve an exact finite range threshold even when its printed float is inf."""
def range_tail_squared(squared,count,degrees):
    from PyFLASH._numeric_scaling import _rational_sqrt,_rational_log,_t_tail_squared
    if count==2:return _t_tail_squared(squared/2,degrees)
    threshold=_rational_sqrt(squared)
    if math.isfinite(threshold):return range_tail(threshold,count,degrees)
    bound=_t_tail_squared(squared/2,degrees)
    if bound==0:return 0.
    log_threshold=_rational_log(squared)/2
    constant=math.log(2)+(degrees/2)*math.log(degrees/2)-float(gammaln(degrees/2))
    def integrand(width):
        if width<=0:return 0.
        return math.exp((degrees-1)*math.log(width))*_normal_range_tail(width,count)
    # exp(-df*w*w/(2*q*q)) differs from one by below 1e-600 at these
    # unrepresentable widths. Keep the chi-scale normalization in log form.
    moment=quad(integrand,0,math.inf,epsabs=0,epsrel=2e-11,limit=200)[0]
    return math.exp(constant-degrees*log_threshold+math.log(moment))

