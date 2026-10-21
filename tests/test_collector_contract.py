"""Collector state, record ownership and all figure attachment options."""
from copy import deepcopy
import json
import pytest
from reproducibility import collector_contract as contract


@pytest.mark.parametrize('case',contract.cases(),ids=lambda row:row['key'])
def test_complete_collector_trace(case):
    original=deepcopy(case)
    assert contract.production(case)==case['expected']
    assert case==original


def test_original_collector_answers_and_failures_are_retained():
    fixture=contract.check_identity()
    assert len(fixture['rows'])==481
    assert sum(row['original_failure'] for row in fixture['rows'])==32


def test_every_collector_owner_requires_its_complete_cases():
    from reproducibility.run import inventory
    keys={case['key'] for case in contract.cases()}
    complete={row['capability']:row for row in inventory(keys)}
    partial={row['capability']:row for row in inventory(keys-{'collector.10','collector.448','collector.464'})}
    for owner in contract.CAPABILITIES:
        assert complete[owner]['status']=='validated-complete-contract'
        assert partial[owner]['status']!='validated-complete-contract'


def test_modified_collector_answer_fails_identity(monkeypatch,tmp_path):
    fixture=json.loads(contract.FIXTURE.read_text(encoding='utf-8'))
    fixture['rows'][0]['expected']['final_records']=[{'kind':'incorrect'}]
    altered=tmp_path/'altered.json';altered.write_text(json.dumps(fixture),encoding='utf-8');monkeypatch.setattr(contract,'FIXTURE',altered)
    with pytest.raises(ValueError,match='differ from original'):contract.check_identity()
