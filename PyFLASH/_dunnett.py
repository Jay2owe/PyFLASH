"""Prototype deterministic Dunnett tail using shared-control conditioning."""
import math
from PyFLASH._cache import bounded_lru_cache as lru_cache
import numpy as np
from scipy.integrate import quad
from scipy.special import ndtr,gammaln,roots_hermitenorm
from scipy.stats import t

_NORMAL_RULES = [(nodes,weights/math.sqrt(2*math.pi))
         for nodes,weights in [roots_hermitenorm(order) for order in (32,64,128,256)]]

@lru_cache(maxsize=256)
def _probability(threshold, sizes, control_size, df, alternative):
    if alternative=='less':threshold=-threshold
    if alternative=='two-sided':threshold=abs(threshold)
    if math.isnan(threshold):return math.nan
    if len(sizes)==1:
        return float(2*t.sf(abs(threshold),df) if alternative=='two-sided' else t.sf(threshold,df))
    if threshold==math.inf:return 0.
    if threshold==-math.inf:return 1.
    if threshold==0 and alternative=='two-sided':return 1.
    weights=np.sqrt(np.asarray(sizes,float)/control_size)
    scales=np.sqrt(1+np.asarray(sizes,float)/control_size)
    log_constant=math.log(2)+(df/2)*math.log(df/2)-float(gammaln(df/2))
    normal_constant=1/math.sqrt(2*math.pi)
    def conditional(scale):
        previous=None
        for nodes,weights_normal in _NORMAL_RULES:
            upper=threshold*scale*scales[None,:]+nodes[:,None]*weights[None,:]
            if alternative=='two-sided':
                lower=-threshold*scale*scales[None,:]+nodes[:,None]*weights[None,:]
                outside=ndtr(lower)+ndtr(-upper)
            else:outside=ndtr(-upper)
            with np.errstate(divide='ignore'):
                union=-np.expm1(np.log1p(-np.minimum(outside,1.)).sum(axis=1))
            answer=float(weights_normal@union)
            if previous is not None and abs(answer-previous)<=2e-12*abs(answer):
                return answer
            previous=answer
        def integrand(shared):
            upper=threshold*scale*scales+shared*weights
            if alternative=='two-sided':
                lower=-threshold*scale*scales+shared*weights
                outside=ndtr(lower)+ndtr(-upper)
            else:outside=ndtr(-upper)
            if np.any(outside>=1):union=1.
            else:union=-math.expm1(float(np.log1p(-outside).sum()))
            return union*math.exp(-shared*shared/2)*normal_constant
        return quad(integrand,-math.inf,math.inf,epsabs=0,epsrel=2e-12,limit=200)[0]
    def radial(scale):
        if scale<=0:return 0.
        density=math.exp(log_constant+(df-1)*math.log(scale)-df*scale*scale/2)
        return conditional(scale)*density
    stretch=max(1.,abs(threshold)/math.sqrt(df))
    return quad(lambda q:radial(q/stretch)/stretch,0,math.inf,
                epsabs=0,epsrel=2e-11,limit=200)[0]

