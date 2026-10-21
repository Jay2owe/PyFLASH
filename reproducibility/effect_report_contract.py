"""Full effect-report answers composed from independently accepted equations."""
from pathlib import Path
from functools import lru_cache
import hashlib
import json
import math
import numpy as np

FIXTURE = Path(__file__).with_name('fixtures') / 'effect_report_reference_v2.json'

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
    if isinstance(value, dict):
        return {key: clean(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [clean(item) for item in value]
    return None if isinstance(value, float) and not math.isfinite(value) else value

def production(case):
    from PyFLASH.stats_extra import effect_sizes_for_test
    options = json.loads(json.dumps(case['parameters']))
    if case['rng_kind'] == 'generator':
        options['random_state'] = np.random.default_rng(case['seed'])
    elif case['rng_kind'] == 'random-state':
        options['random_state'] = np.random.RandomState(case['seed'])
    elif case['rng_kind'] == 'integer':
        options['random_state'] = case['seed']
    return clean(effect_sizes_for_test(**options))

def equal(actual, answer):
    if isinstance(actual, dict):
        return (isinstance(answer, dict) and actual.keys() == answer.keys()
                and all(equal(actual[key], answer[key]) for key in actual))
    if isinstance(actual, list):
        return (isinstance(answer, list) and len(actual) == len(answer)
                and all(equal(a, b) for a, b in zip(actual, answer)))
    if actual is None or answer is None:
        return actual is answer
    if isinstance(actual, (float, int)) and isinstance(answer, (float, int)):
        return math.isclose(actual, answer, rel_tol=1e-9, abs_tol=1e-12)
    return actual == answer

def check_identity():
    data = fixture()
    root = Path(__file__).parent
    definitions = json.dumps(cases(), sort_keys=True, separators=(',', ':')).encode('utf-8')
    if hashlib.sha256(definitions).hexdigest() != data['definitions_sha256']:
        raise ValueError('Effect-report frozen requests changed')
    for name, expected_hash in data['source_manifest'].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected_hash:
            raise ValueError('Effect-report independent reference source changed: ' + name)
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != data['adapter_sha256']:
        raise ValueError('Effect-report frozen adapter changed')
    return data
