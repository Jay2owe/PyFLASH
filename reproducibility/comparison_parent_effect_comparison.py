import math
from reproducibility.one_way_contract import equal as parent_equal

def equal(actual,expected,path=()):
    if isinstance(expected,dict):return isinstance(actual,dict) and actual.keys()==expected.keys() and all(equal(actual[k],expected[k],path+(k,)) for k in expected)
    if isinstance(expected,list):return isinstance(actual,list) and len(actual)==len(expected) and all(equal(a,b,path+(i,)) for i,(a,b) in enumerate(zip(actual,expected)))
    if isinstance(actual,(int,float)) and isinstance(expected,(int,float)) and any(isinstance(k,str) and k.startswith('Effect ') for k in path):
        return math.isclose(actual,expected,rel_tol=1e-9,abs_tol=0.)
    return parent_equal(actual,expected,path)
