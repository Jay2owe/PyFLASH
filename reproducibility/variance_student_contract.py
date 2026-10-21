"""Complete frozen variance-screen and independent-sample report contracts."""
from pathlib import Path
import hashlib,json,math,warnings
from PyFLASH import stats
from reproducibility import variance_student_mathematical_reference as mathematics
FIXTURE=Path(__file__).with_name('fixtures')/'variance_student_complete_reference.json'

def cases():return json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']

def check_identity():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'))
    for path,expected in fixture['source_manifest'].items():
        if hashlib.sha256((Path(__file__).parent/path).read_bytes()).hexdigest()!=expected:
            raise ValueError('Original variance/t evidence changed: '+path)
    if hashlib.sha256(Path(mathematics.__file__).read_bytes()).hexdigest()!=fixture['mathematical_reference_sha256']:
        raise ValueError('Independent variance/t mathematics changed')
    original=json.loads((Path(__file__).parent/'reference-sources/variance-student/frozen-before.json').read_text(encoding='utf-8'))
    if fixture['rows']!=original['rows']:
        raise ValueError('Variance/t inputs or answers differ from frozen before-correction evidence')
    return fixture

def production(kind, parameters):
    raw = {'caller-note': 'retained'}
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            if kind == 'variance':
                output = stats.test_equal_variance(results_dict=raw, **parameters)
                return mathematics.clean({'output': output, 'results_dict': raw})
            p, labels, overall, result, label = stats.runITTest(results_dict=raw, **parameters)
            return mathematics.clean({'pvalues': p, 'annotations': labels, 'overall': overall, 'results_dict': result, 'method': label})
    except Exception as error:
        return {'error': type(error).__name__}

def equal(actual, answer, path=()):
    if isinstance(answer, dict):
        return isinstance(actual, dict) and actual.keys() == answer.keys() and all((equal(actual[k], answer[k], path + (k,)) for k in answer))
    if isinstance(answer, list):
        return isinstance(actual, list) and len(actual) == len(answer) and all((equal(a, b, path + (i,)) for i, (a, b) in enumerate(zip(actual, answer))))
    if isinstance(answer, bool) or isinstance(actual, bool):
        return type(actual) == type(answer) and actual == answer
    if isinstance(actual, (int, float)) and isinstance(answer, (int, float)):
        probability = ('overall' in path and path[-1] == 1) or any((key in {'pvalues', 'pvalue', 'Posthoc-Uncorrected'} for key in path))
        if path and isinstance(path[-1], int) and (path[-1] == 1) and any((str(k).startswith(('Variance ', "Student's T", "Welch's T", 'Independent T', 'Equal variance')) for k in path)):
            probability = True
        return math.isclose(actual, answer, rel_tol=1e-09, abs_tol=0.0 if probability else 1e-12)
    return type(actual) == type(answer) and actual == answer
