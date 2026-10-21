"""Neutral construction of ordinal response inputs and supplied model states."""
import numpy as np
import pandas as pd
from scipy import sparse

KINDS = ('list', 'tuple', 'array', 'fortran', 'strided', 'dataframe', 'csr', 'csc', 'coo')


def model_for(case):
    from mord import LogisticIT
    from PyFLASH.modelling import _PyFLASHOrdinalLogistic
    model = _PyFLASHOrdinalLogistic()
    model.classes_ = np.arange(len(case['theta']) + 1) + case['first_label']
    model.model_ = LogisticIT()
    model.model_.coef_ = np.array(case['coef'])
    model.model_.theta_ = np.array(case['theta'])
    model.model_.classes_ = model.classes_.copy()
    return model


def represent(values, kind):
    array = np.array(values, dtype=float)
    if kind == 'list':
        return array.tolist()
    if kind == 'tuple':
        return tuple(map(tuple, array.tolist()))
    if kind == 'fortran':
        return np.asfortranarray(array)
    if kind == 'strided':
        backing = np.empty((len(array), array.shape[1] * 2))
        backing[:, ::2] = array
        return backing[:, ::2]
    if kind == 'dataframe':
        return pd.DataFrame(array)
    if kind in ('csr', 'csc', 'coo'):
        return getattr(sparse, kind + '_matrix')(array)
    return array
