"""Native R and published Python statistics means on identical represented inputs.

Produces reference-only numbers. The exact Python mean remains independent of
the PyFLASH candidate. R disagreements are retained, never overwritten.
"""
from statistics import mean
import math

def cases():
    samples = {
        'ordinary': [1., 3., 5.], 'missing': [1., None, 3.],
        'all-missing': [None, None], 'single': [7.], 'zero': [0., 0.],
        'equal-large': [1e308, 1e308], 'mixed-large': [1e308, 5e307],
        'cancel-tiny': [1e308, 1e-300, -1e308],
        'cancel-small': [1e308, 1., -1e308],
        'negative-large': [-1e308, -1e308],
        'equal-small': [5e-324, 5e-324],
        'unequal-small': [5e-324, 1e-323],
        'baseline-large': [1e16, 1e16+2., 1e16+4.],
        'positive-infinite': [math.inf, 3.],
        'negative-infinite': [-math.inf, 3.],
        'mixed-infinite': [math.inf, -math.inf],
    }
    return [{'key': key, 'values': values} for key, values in samples.items()]

def query(case):
    def token(value):
        if value is None: return 'NA_real_'
        if value == math.inf: return 'Inf'
        if value == -math.inf: return '-Inf'
        return repr(value)
    return {'key': case['key'], 'code': 'mean(c('+','.join(map(token, case['values']))+'), na.rm=TRUE)'}

def published_python_mean(case):
    finite = [value for value in case['values'] if value is not None]
    return float(mean(finite)) if finite else math.nan
