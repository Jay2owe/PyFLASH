"""Complete application audit reports retain frozen requests and answers."""
from copy import deepcopy
import json
import pytest
from reproducibility import audit_parent_contract as contract

@pytest.mark.parametrize('case', contract.cases(), ids=lambda row: row['key'])
def test_full_application_audit_matches_independent_answer(case):
    original = deepcopy(case)
    assert contract.equal(contract.production(case), case['expected'])
    assert case == original

def test_original_audit_failures_are_retained():
    fixture = contract.check_identity()
    assert len(fixture['rows']) == 628
    assert sum(row['original_failure'] for row in fixture['rows']) == 109

def test_correction_unavailability_keeps_original_reason():
    from PyFLASH import stats
    raw = {'Correction-Unavailable': ['original explanation', float('nan')]}
    stats._audit_to_results_dict({'alpha': .05, 'permutation': None, 'skipped': 'later explanation'}, [], raw, {})
    assert raw['Correction-Unavailable'][0] == 'original explanation'

def test_changed_frozen_audit_answer_fails_identity(monkeypatch, tmp_path):
    payload = json.loads(contract.FIXTURE.read_text())
    payload['rows'][0]['expected']['results_strings'] = {'changed': 'answer'}
    changed = tmp_path/'changed.json'
    changed.write_text(json.dumps(payload))
    monkeypatch.setattr(contract, 'FIXTURE', changed)
    with pytest.raises(ValueError, match='differ from frozen'):
        contract.check_identity()
