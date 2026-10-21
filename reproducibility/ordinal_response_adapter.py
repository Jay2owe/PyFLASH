"""Observe complete public wrapper responses without fitting parameters."""
def production(case):
    import numpy as np,pandas as pd
    from scipy.sparse import csr_matrix
    from mord import LogisticIT
    from PyFLASH.modelling import _PyFLASHOrdinalLogistic
    model=_PyFLASHOrdinalLogistic();model.classes_=np.arange(len(case['theta'])+1)+case['first_label']
    model.model_=LogisticIT();model.model_.coef_=np.array(case['coef']);model.model_.theta_=np.array(case['theta'])
    model.model_.classes_=model.classes_.copy()
    x=np.array(case['x'])
    if case['container']=='dataframe':x=pd.DataFrame(x)
    elif case['container']=='csr':x=csr_matrix(x)
    return {'predictions':model.predict(x).tolist(),'probabilities':model.predict_proba(x).tolist()}

def equal(actual,expected):
    import math
    if isinstance(expected,dict):return isinstance(actual,dict) and actual.keys()==expected.keys() and all(equal(actual[k],expected[k]) for k in expected)
    if isinstance(expected,list):return isinstance(actual,list) and len(actual)==len(expected) and all(equal(a,b) for a,b in zip(actual,expected))
    if isinstance(expected,(float,int)):return isinstance(actual,(float,int)) and math.isclose(actual,expected,rel_tol=1e-9,abs_tol=0.)
    return actual==expected
