"""Every returned record field agrees with the independent literal schema."""
from copy import deepcopy
import json
import pytest
from reproducibility import regression_record_contract as contract


@pytest.mark.parametrize('case',contract.cases(),ids=lambda row:row['key'])
def test_complete_supplied_input_record(case):
    original=deepcopy(case)
    assert contract.production(case)==case['expected']
    assert case==original


def test_original_requests_answers_and_failures_are_retained():
    fixture=contract.check_identity()
    assert len(fixture['rows'])==233
    assert sum(row['original_failure'] for row in fixture['rows'])==21


def test_every_record_owner_requires_its_complete_case_set():
    from reproducibility.run import inventory
    cases=contract.cases();keys={case['key'] for case in cases}
    rows={row['capability']:row for row in inventory(keys)}
    for owner in contract.CAPABILITIES.values():
        assert rows[owner]['status']=='validated-complete-contract'
        required={case['key'] for case in cases if contract.capability(case)==owner}
        partial={row['capability']:row for row in inventory(keys-{next(iter(required))})}
        assert partial[owner]['status']!='validated-complete-contract'


def test_replacing_record_answer_fails_identity(monkeypatch,tmp_path):
    payload=json.loads(contract.FIXTURE.read_text(encoding='utf-8'));payload['rows'][0]['expected']['headline']='Incorrect result'
    altered=tmp_path/'altered.json';altered.write_text(json.dumps(payload),encoding='utf-8');monkeypatch.setattr(contract,'FIXTURE',altered)
    with pytest.raises(ValueError,match='differ from before-correction'):contract.check_identity()
