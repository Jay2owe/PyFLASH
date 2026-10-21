import math
from copy import deepcopy
import numpy as np
from PyFLASH import report

def decode(value):
    if isinstance(value,dict):return {key:decode(item) for key,item in value.items()}
    if isinstance(value,list):return [decode(item) for item in value]
    return {'__nan__':math.nan,'__inf__':math.inf}.get(value,value) if isinstance(value,str) else value

def production(case):
    parameters=decode(deepcopy(case['parameters']))
    if case.get('container'):
        name='covariates' if case['variant'].startswith('covariates') else 'predictors'
        parameters[name]=tuple(parameters[name]) if case['container']=='tuple' else np.asarray(parameters[name])
    function={'correlation':report.build_correlation_record,'multivariable_regression':report.build_multivariable_regression_record,
        'linear_model':report.build_linear_model_record,'stars':report.significance_stars}[case['kind']]
    try:return function(**parameters)
    except Exception as error:return {'error':type(error).__name__}
