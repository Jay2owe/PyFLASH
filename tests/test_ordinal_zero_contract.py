"""Complete zero-feature reports and preserved general-fit input obligations."""
import json
from copy import deepcopy
import pytest
from reproducibility import ordinal_zero_contract as contract

@pytest.mark.parametrize('case',contract.cases(),ids=lambda row:row['key'])
def test_complete_fit_against_exact_zero_feature_reference(case):
    original=deepcopy(case);answer=contract.reference.report(case)
    assert contract.equal(answer,case['expected'])
    assert contract.equal(contract.production(case),answer)
    assert case==original

def test_original_failures_and_native_witnesses_are_retained():
    fixture=contract.check_identity();assert len(fixture['rows'])==108
    assert sum(row['original_failure'] for row in fixture['rows'])==60
    assert all(row['native_agrees'] for row in fixture['rows'])

def test_zero_feature_controls_leave_general_fit_options_open():
    from reproducibility.run import inventory
    keys={row['key'] for row in contract.cases()}
    rows=inventory(keys)
    for capability in contract.CAPABILITIES:
        owner=next(row for row in rows if row['capability']==capability)
        assert owner['status']=='partially-validated-contract'

def test_altered_fit_answer_fails_identity(tmp_path,monkeypatch):
    fixture=json.loads(contract.FIXTURE.read_text(encoding='utf-8'))
    fixture['rows'][0]['expected']['theta'][0]=123.
    path=tmp_path/'changed.json';path.write_text(json.dumps(fixture),encoding='utf-8');monkeypatch.setattr(contract,'FIXTURE',path)
    with pytest.raises(ValueError,match='differ from original'):contract.check_identity()

@pytest.mark.parametrize('case',contract.regressions(),ids=lambda row:row['request']['key'])
def test_original_nonzero_inputs_match_reviewed_independent_native_fits(case):
    from reproducibility import ordinal_fitting_contract as fitted
    # The original approximate answers remain immutable in the retained
    # archive. The documented precision repair is locked to native answers.
    alias=next(row for row in fitted.historical_cases() if row['request_key']==case['request']['key'])
    assert alias['full_request']==case['request'] and alias['original_answer']==case['original']
    native=next(row for row in fitted.cases() if row['case']['key']==alias['numeric_case_key'])
    actual=fitted.observe(native['case'],container=alias['container'],first_label=alias['first_label'],max_iter=alias['max_iter'])
    assert fitted.equal(actual,fitted.expected_for_label(native,alias['first_label']))

def test_direct_fit_reports_the_declared_missing_dependency(monkeypatch):
    import numpy as np
    from PyFLASH import _optional
    from PyFLASH.modelling import _PyFLASHOrdinalLogistic
    monkeypatch.setattr(_optional,'optional_import',lambda name:None)
    with pytest.raises(ImportError,match=r'PyFLASH-analysis\[classification\]'):
        _PyFLASHOrdinalLogistic().fit(np.zeros((4,1)),np.array([0,0,1,1]))
