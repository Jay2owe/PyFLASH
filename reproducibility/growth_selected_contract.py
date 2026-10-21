"""Complete outputs for selected nonlinear fits, with limited declared scope.

The frozen native R expressions solve the symbolic Hessian stationary equations;
they are mathematical references, not equivalence to a published fitting package.
"""
import hashlib
import json
import math
from pathlib import Path
import random

FIXTURE = Path(__file__).parent / 'fixtures/growth_selected_reference.json'
NAMES = {'exponential': ['amplitude', 'rate', 'offset'],
         'logistic': ['bottom', 'top', 'ec50', 'hill']}


def cases():
    rng = random.Random(20261004)
    x = [.5, 1., 1.7, 2.3, 3.8, 5.1, 7., 9., 12., 15., 19.]
    patterns = {
        'linear': [1.3*v+2 for v in x],
        'exponential_growth': [2*math.exp(.12*v)+1.7 for v in x],
        'exponential_decay': [5*math.exp(-.15*v)+2 for v in x],
        'logistic_growth': [1+8/(1+(4/v)**1.5) for v in x],
        'logistic_decay': [8-7/(1+(5/v)**2.1) for v in x]}
    rows = []
    for pattern, clean in patterns.items():
        y = [value+rng.uniform(-.08, .08) for value in clean]
        if pattern == 'linear':
            continue
        model = pattern.split('_')[0]
        for variant in ['ordinary', 'unsorted_missing']:
            xx, yy = list(x), list(y)
            if variant == 'unsorted_missing':
                xx, yy = list(reversed(xx))+[None, 3, 'Inf'], list(reversed(yy))+[1, None, 2]
            rows.append({'key': f'growth.{pattern}.{model}.{variant}',
                'capability': 'PyFLASH.stats_extra.fit_growth_curve',
                'parameters': {'x': xx, 'y': yy, 'model': model,
                               'prediction_x': [.25, .75, 1.5, 3., 6., 10., 16., 22.]}})
    return rows


def normalised_identity(row):
    p = row['parameters']
    pairs = sorted((float(x), float(y)) for x, y in zip(p['x'], p['y'])
        if x is not None and y is not None and math.isfinite(float(x)) and math.isfinite(float(y)))
    canonical = {**p, 'x': [v[0] for v in pairs], 'y': [v[1] for v in pairs]}
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def production(row):
    from PyFLASH.stats_extra import fit_growth_curve
    p = row['parameters']
    answer = fit_growth_curve([math.nan if v is None else float(v) for v in p['x']],
                             [math.nan if v is None else float(v) for v in p['y']], model=p['model'])
    assert set(answer) == {'model', 'params', 'r_squared', 'aic', 'n', 'predict', 'all_models'}
    assert answer['model'] == p['model']
    names = NAMES[p['model']]
    assert list(answer['params']) == names and list(answer['all_models']) == [p['model']]
    return [2 if p['model'] == 'exponential' else 3, answer['n'],
            *[answer['params'][name]['value'] for name in names],
            *[answer['params'][name]['stderr'] for name in names], answer['r_squared'], answer['aic'],
            *answer['predict'](p['prediction_x']).tolist(), answer['all_models'][p['model']]['aic']]
