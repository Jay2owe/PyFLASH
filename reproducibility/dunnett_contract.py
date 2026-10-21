"""Full Dunnett reports from frozen independent native-R conditional integrals."""
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import math
import numpy as np

FIXTURE = Path(__file__).with_name('fixtures') / 'dunnett_reference.json'

@lru_cache(maxsize=1)
def fixture():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))

@lru_cache(maxsize=1)
def _rows():
    return {row['case']['key']: row for row in fixture()['rows']}

def cases():
    return json.loads(json.dumps([row['case'] for row in fixture()['rows']]))

def expected(case):
    return json.loads(json.dumps(_rows()[case['key']]['expected']))

def clean(value):
    if isinstance(value, dict): return {key: clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)): return [clean(item) for item in value]
    return str(value) if isinstance(value, float) and not math.isfinite(value) else value

def production(case):
    from PyFLASH.stats_extra import dunnett_vs_control
    options = json.loads(json.dumps(case['parameters']))
    if case['rng_kind'] == 'random-state': options['random_state'] = np.random.RandomState(case['seed'])
    elif case['rng_kind'] == 'generator': options['random_state'] = np.random.default_rng(case['seed'])
    elif case['rng_kind'] == 'integer': options['random_state'] = case['seed']
    result = dunnett_vs_control(**options)
    return {'columns': list(result.columns), 'rows': clean(result.astype(object).values.tolist())}

def equal(actual, answer):
    return actual['columns'] == answer['columns'] and len(actual['rows']) == len(answer['rows']) and all(
        x[0] == y[0] and all(u == v if isinstance(u, str) or isinstance(v, str) else
            math.isclose(u, v, rel_tol=1e-9, abs_tol=0. if j == 2 else 1e-12)
            for j, (u, v) in enumerate(zip(x, y)) if j > 0)
        for x, y in zip(actual['rows'], answer['rows']))

def check_identity():
    data = fixture()
    root = Path(__file__).parent
    definitions = json.dumps(cases(), sort_keys=True, separators=(',', ':')).encode('utf-8')
    if hashlib.sha256(definitions).hexdigest() != data['definitions_sha256']:
        raise ValueError('Frozen Dunnett requests changed')
    for name, expected_hash in data['source_manifest'].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected_hash:
            raise ValueError('Dunnett independent reference identity changed: ' + name)
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != data['adapter_sha256']:
        raise ValueError('Dunnett adapter changed')
    return data
