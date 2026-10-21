"""Dimensionless outputs retain accepted answers under exact binary unit changes."""
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import math

FIXTURE = Path(__file__).with_name('fixtures') / 'finite_scale_reference.json'

@lru_cache(maxsize=1)
def fixture():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))

def cases():
    return json.loads(json.dumps(fixture()['rows']))

def clean(value):
    if isinstance(value, dict): return {key: clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)): return [clean(item) for item in value]
    return str(value) if isinstance(value, float) and not math.isfinite(value) else value

def production(case):
    from PyFLASH import stats_extra
    result = getattr(stats_extra, case['method'])(**case['parameters'])
    if case['method'] == 'dunnett_vs_control':
        return {'columns': list(result.columns), 'rows': clean(result.astype(object).values.tolist())}
    return clean(result)

def equal(actual, answer, *, probability=False):
    if isinstance(actual, dict):
        return isinstance(answer, dict) and actual.keys() == answer.keys() and all(
            equal(actual[k], answer[k]) for k in actual)
    if isinstance(actual, list):
        return isinstance(answer, list) and len(actual) == len(answer) and all(
            equal(a, b, probability=(len(actual) == 3 and isinstance(actual[0], str) and i == 2))
            for i, (a, b) in enumerate(zip(actual, answer)))
    if isinstance(actual, (float, int)) and isinstance(answer, (float, int)):
        return math.isclose(actual, answer, rel_tol=1e-9, abs_tol=0. if probability else 1e-12)
    return actual == answer

def check_identity():
    data = fixture()
    root = Path(__file__).parent
    for name, expected in data['source_manifest'].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError('Unit-invariance reference identity changed: ' + name)
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != data['adapter_sha256']:
        raise ValueError('Unit-invariance adapter changed')
    for row in data['rows']:
        originals = row['unscaled_groups'][:2] if row['method'] != 'dunnett_vs_control' else row['unscaled_groups']
        raw = [row['parameters']['a'], row['parameters']['b']] if row['method'] != 'dunnett_vs_control' else row['parameters']['groups']
        if raw != [[math.ldexp(value, row['binary_exponent']) for value in group] for group in originals]:
            raise ValueError('Exact binary unit-change inputs changed')
    return data
