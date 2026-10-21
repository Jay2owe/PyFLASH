"""Observe full fitted state and held-out responses of the actual wrapper."""
def production(case,cls=None):
    import numpy as np,pandas as pd
    from scipy.sparse import csr_matrix
    if cls is None:
        from PyFLASH.modelling import _PyFLASHOrdinalLogistic as cls
    labels=np.concatenate([np.repeat(case['first_label']+j,n) for j,n in enumerate(case['counts'])])
    x=np.tile(case['constant'],(len(labels),1));held=np.array(case['held'])
    if case['container']=='dataframe':x,held=pd.DataFrame(x),pd.DataFrame(held)
    elif case['container']=='csr':x,held=csr_matrix(x),csr_matrix(held)
    model=cls(alpha=case['alpha'],max_iter=case['max_iter'])
    try:
        returned=model.fit(x,labels)
        return {'returns_self':returned is model,'coef':model.model_.coef_.tolist(),
                'theta':model.model_.theta_.tolist(),'classes':model.classes_.tolist(),
                'predictions':model.predict(held).tolist(),'probabilities':model.predict_proba(held).tolist()}
    except Exception as error:
        return {'error_type':type(error).__name__,'error':str(error)}
