"""Observe the real fitted wrapper on declared zero-feature controls."""
import math
import numpy as np
from PyFLASH.modelling import _PyFLASHOrdinalLogistic
RTOL=1e-9
ATOL=0.
def equal(a,b):
    if isinstance(b,dict):return isinstance(a,dict) and a.keys()==b.keys() and all(equal(a[k],b[k]) for k in b)
    if isinstance(b,list):return isinstance(a,list) and len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
    if isinstance(a,(int,float)) and isinstance(b,(int,float)):return math.isclose(a,b,rel_tol=RTOL,abs_tol=ATOL)
    return a==b

def production(case):
    labels=np.concatenate([np.repeat(case['first_label']+j,n) for j,n in enumerate(case['counts'])])
    x=np.zeros((len(labels),case['features']));held=np.zeros((case['test_rows'],case['features']))
    model=_PyFLASHOrdinalLogistic(alpha=case['alpha'],max_iter=case['max_iter'])
    model.fit(x,labels)
    return {'coef':model.model_.coef_.tolist(),'theta':model.model_.theta_.tolist(),'classes':model.classes_.tolist(),
        'predictions':model.predict(held).tolist(),'probabilities':model.predict_proba(held).tolist()}

import pandas as pd
from scipy.sparse import csr_matrix

def observe(cls,request):
    x=np.asarray(request['x']);held=np.asarray(request['held'])
    if request['container']=='dataframe':x,held=pd.DataFrame(x),pd.DataFrame(held)
    elif request['container']=='csr':x,held=csr_matrix(x),csr_matrix(held)
    model=cls(alpha=request['alpha'],max_iter=request['max_iter']);returned=model.fit(x,np.asarray(request['y']))
    return {'returns_self':returned is model,'parameters':model.get_params(),'coef':model.model_.coef_.tolist(),
        'theta':model.model_.theta_.tolist(),'classes':model.classes_.tolist(),'prediction':model.predict(held).tolist(),
        'probabilities':model.predict_proba(held).tolist()}
