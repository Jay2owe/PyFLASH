"""Every accepted supplied record preserves its complete human-readable digest."""
from copy import deepcopy
import json
import pytest
from reproducibility import record_digest_contract as contract


@pytest.mark.parametrize('case',contract.cases(),ids=lambda row:row['key'])
def test_complete_digest(case):
    original=deepcopy(case)
    assert contract.production(case)==case['expected']
    assert case==original


def test_original_digest_requests_and_answers_are_retained():
    fixture=contract.check_identity()
    assert len(fixture['rows'])==7787
    assert not any(row['original_failure'] for row in fixture['rows'])


def test_complete_digest_owner_requires_every_case():
    from reproducibility.run import inventory
    keys={case['key'] for case in contract.cases()}
    rows={row['capability']:row for row in inventory(keys)}
    assert rows['PyFLASH.report.render_digest']['status']=='validated-complete-contract'
    rows={row['capability']:row for row in inventory(keys-{'record-digest.0'})}
    assert rows['PyFLASH.report.render_digest']['status']!='validated-complete-contract'


def test_changed_digest_answer_is_rejected(monkeypatch,tmp_path):
    fixture=json.loads(contract.FIXTURE.read_text(encoding='utf-8'))
    fixture['rows'][0]['expected']+='Incorrect line\n'
    altered=tmp_path/'altered.json';altered.write_text(json.dumps(fixture),encoding='utf-8')
    monkeypatch.setattr(contract,'FIXTURE',altered)
    with pytest.raises(ValueError,match='differ from original'):contract.check_identity()
