"""Complete frozen rank-sum reports with original group positions."""
from pathlib import Path
import hashlib,json,math,warnings
from PyFLASH import stats
from reproducibility import mann_whitney_mathematical_reference as mathematics
FIXTURE=Path(__file__).with_name('fixtures')/'mann_whitney_complete_reference.json'

def cases():return json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']

def check_identity():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'))
    for path,expected in fixture['source_manifest'].items():
        if hashlib.sha256((Path(__file__).parent/path).read_bytes()).hexdigest()!=expected:
            raise ValueError('Original Mann-Whitney evidence changed: '+path)
    if hashlib.sha256(Path(mathematics.__file__).read_bytes()).hexdigest()!=fixture['mathematical_reference_sha256']:
        raise ValueError('Independent rank-sum mathematics changed')
    original=json.loads((Path(__file__).parent/'reference-sources/mann-whitney/frozen-before.json').read_text(encoding='utf-8'))
    if fixture['rows']!=original['rows']:
        raise ValueError('Rank-sum inputs or answers differ from frozen before-correction evidence')
    return fixture

def production(parameters):
    raw = {'caller-note': 'retained'}
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            p, labels, overall, result, method = stats.mwu_multiple_comparisons(results_dict=raw, **parameters)
        return mathematics.clean({'pvalues': p, 'annotations': labels, 'overall': overall, 'results_dict': result, 'method': method})
    except Exception as error:
        return {'error': type(error).__name__}

def equal(actual, expected, path=()):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and actual.keys() == expected.keys() and all((equal(actual[k], expected[k], path + (k,)) for k in expected))
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all((equal(a, b, path + (i,)) for i, (a, b) in enumerate(zip(actual, expected))))
    if isinstance(actual, (float, int)) and isinstance(expected, (float, int)):
        is_p = 'pvalues' in path or 'Posthoc-Uncorrected' in path or ('overall' in path and path[path.index('overall') + 1] == 1) or ('Mann-Whitney U' in path and path[path.index('Mann-Whitney U') + 1] == 1)
        return math.isclose(actual, expected, rel_tol=1e-09, abs_tol=0.0 if is_p else 1e-12)
    return type(actual) == type(expected) and actual == expected
