"""Full variance/t results, undefined inference and invalid requests."""
from copy import deepcopy
import hashlib
from pathlib import Path
import pytest
from reproducibility import variance_student_contract as contract
from reproducibility import variance_student_mathematical_reference as mathematics
from reproducibility import variance_student_validation as validation

@pytest.mark.parametrize('case',contract.cases(),ids=lambda row:row['key'])
def test_complete_report_against_independent_frozen_mathematics(case):
    original=deepcopy(case)
    assert contract.equal(contract.production(case['kind'],case['parameters']),case['expected'])
    assert case==original

def test_original_632_failures_and_independent_code_are_preserved():
    fixture=contract.check_identity()
    assert len(fixture['rows'])==1541
    assert sum(r['original_failure'] for r in fixture['rows'])==632

def test_complete_promotion_requires_every_report_and_native_corroboration():
    from reproducibility.run import inventory
    keys={r['key'] for r in contract.cases()}|{r['query']['key'] for r in validation.native_cases() if r['role']=='independent-native-corroboration'}
    from reproducibility.extreme_inference_contract import required_keys as extreme_keys
    keys.update(extreme_keys('student'))
    capabilities={'PyFLASH.stats.test_equal_variance','PyFLASH.stats.runITTest'}
    complete={r['capability']:r for r in inventory(keys) if r['capability'] in capabilities}
    assert len(complete)==2 and all(r['status']=='validated-complete-contract' for r in complete.values())
    for capability,row in complete.items():
        contracts=row['executed_subcontracts'].split(';')
        for missing in (next(k for k in contracts if '.complete.' in k),next(k for k in contracts if '-native.' in k)):
            assert next(r for r in inventory(keys-{missing}) if r['capability']==capability)['status']!='validated-complete-contract'

@pytest.mark.parametrize('case',[r for r in validation.native_cases() if r['role']=='independent-native-corroboration'],ids=lambda r:r['query']['key'])
def test_complete_native_reference_answers_are_retained(case):
    import json
    directory=Path(contract.__file__).parent/'reference-sources/variance-student'
    source='fligner-exact-rank-native-confirmed-fligner-exact-ranks-results.json' if case['query']['key'].endswith('.exact-rank-inputs') else 'variance-student-native-confirmed-variance-student-results.json'
    payload=json.loads((directory/source).read_text())
    row=next(r for r in payload['rows'] if r['key']==case['query']['key'])
    from reproducibility.reference_runtime import values
    assert validation.native_equal(values(row),case['expected'])
