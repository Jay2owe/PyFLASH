"""Preserved complete rank-derived application correction reports."""
from pathlib import Path
from copy import deepcopy
import json, hashlib
from PyFLASH import stats
from PyFLASH.config import Config
from reproducibility import rank_contract, audit_parent_reference as reference
from reproducibility.one_way_contract import clean, equal

FIXTURE = Path(__file__).with_name('fixtures') / 'audit_parent_complete_reference.json'

def cases():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']

def check_identity():
    fixture = json.loads(FIXTURE.read_text(encoding='utf-8'))
    root = Path(__file__).parent
    for path, expected in fixture['source_manifest'].items():
        if hashlib.sha256((root/path).read_bytes()).hexdigest() != expected:
            raise ValueError('Original correction audit evidence changed: '+path)
    original = [row for path in fixture['before_rounds'] for row in json.loads((root/path).read_text(encoding='utf-8'))['rows']]
    if fixture['rows'] != original:
        raise ValueError('Correction audit requests or answers differ from frozen before-correction evidence')
    return fixture

def production(case):
    parent = case['parent']
    answer = rank_contract.production(parent)
    if 'error' in answer:
        return answer
    result = reference.unpack(deepcopy(answer['results_dict']))
    strings = {'caller-note': 'retained'}
    names = ('CORRECTION_AUDIT', 'CORRECTION_RESAMPLES', 'CORRECTION_EXACT_MAX')
    previous = [getattr(Config, name) for name in names]
    try:
        Config.CORRECTION_AUDIT = case['tier']
        Config.CORRECTION_RESAMPLES = parent.get('count', 20000)
        Config.CORRECTION_EXACT_MAX = parent.get('exact_max', 10000)
        audit = stats._run_correction_audit(result, strings, parent['parameters']['comparisons'], Config,
            requested=parent['parameters']['posthoc_correction'], applied=answer['method'])
        return clean({'audit': audit, 'results_dict': result, 'results_strings': strings})
    except Exception as error:
        return {'error': type(error).__name__}
    finally:
        for name, value in zip(names, previous):
            setattr(Config, name, value)

def required_keys():
    return {row['key'] for row in cases()}

def validate(output):
    from reproducibility.normality_association_validation import comparison
    check_identity()
    rows, paired = [], []
    for case in cases():
        actual, answer = production(case), reference.reference(case)
        unchanged = equal(answer, case['expected'])
        rows.append(comparison(case['key'], 'independent-rank-geometry/correction-equations/complete-report-policy',
            'complete-rank-derived-application-audit/no-extra-native-kernel-vote', actual, answer,
            unchanged and equal(actual, answer), unchanged, 'all-numeric-fields-atol-zero', 1e-9, 0.))
        paired.append({'case': case, 'production': actual, 'reference': answer, 'frozen_reference': case['expected']})
    (output/'audit-parent-paired-data.json').write_text(json.dumps({'rows': paired}, indent=2, allow_nan=False), encoding='utf-8')
    return rows
