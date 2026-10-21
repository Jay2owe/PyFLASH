import math,warnings
from copy import deepcopy
from PyFLASH import stats_extra
from reproducibility.one_way_contract import clean

def equal(actual,expected):
    return isinstance(actual,list) and len(actual)==len(expected) and all(
        math.isclose(a,b,rel_tol=1e-9,abs_tol=0.) if isinstance(a,(int,float)) and isinstance(b,(int,float)) else a==b
        for a,b in zip(actual,expected))

def production(case):
    p=deepcopy(case['parameters'])
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        if case['default_options']:
            from PyFLASH.config import Config
            previous=Config.EFFECT_CI_RANDOM_STATE
            try:
                Config.EFFECT_CI_RANDOM_STATE=0;answer=stats_extra.effect_ci(case['a'],case['b'],p['eftype'])
            finally:Config.EFFECT_CI_RANDOM_STATE=previous
        else:answer=stats_extra.effect_ci(case['a'],case['b'],**p)
    return clean(list(answer))
