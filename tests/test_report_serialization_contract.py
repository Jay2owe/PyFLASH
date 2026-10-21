"""Scalar containers and empty/truncated tables retain the declared summary schema."""
from copy import deepcopy
import json
import pytest
from reproducibility import report_serialization_contract as contract


@pytest.mark.parametrize('case',contract.cases(),ids=lambda row:row['key'])
def test_complete_typed_summary(case):
    original=deepcopy(case)
    assert contract.production(case)==case['expected']
    assert case==original


def test_original_summary_requests_answers_and_failures_are_retained():
    fixture=contract.check_identity()
    assert len(fixture['rows'])==78
    assert sum(row['original_failure'] for row in fixture['rows'])==6


def test_every_summary_owner_requires_its_complete_case_set():
    from reproducibility.run import inventory
    cases=contract.cases();keys={case['key'] for case in cases}
    rows={row['capability']:row for row in inventory(keys)}
    for owner in ('PyFLASH.report.coerce','PyFLASH.report.summarize_return'):
        assert rows[owner]['status']=='validated-complete-contract'
        required={case['key'] for case in cases if contract.capability(case)==owner}
        partial={row['capability']:row for row in inventory(keys-{next(iter(required))})}
        assert partial[owner]['status']!='validated-complete-contract'


def test_replacing_summary_answer_fails_identity(monkeypatch,tmp_path):
    payload=json.loads(contract.FIXTURE.read_text(encoding='utf-8'));payload['rows'][0]['expected']='Incorrect summary'
    altered=tmp_path/'altered.json';altered.write_text(json.dumps(payload),encoding='utf-8');monkeypatch.setattr(contract,'FIXTURE',altered)
    with pytest.raises(ValueError,match='differ from before-correction'):contract.check_identity()
