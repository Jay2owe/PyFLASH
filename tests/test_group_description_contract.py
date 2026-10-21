"""Extreme units must retain every descriptive field in reported groups."""
from copy import deepcopy
import json
import pytest
from reproducibility import group_description_contract as contract


@pytest.mark.parametrize('case',contract.cases(),ids=lambda row:row['key'])
def test_complete_group_description_matches_independent_moments(case):
    before=deepcopy(case)
    assert contract.equal(contract.production(case),case['expected'])
    assert case==before


def test_description_evidence_preserves_all_original_failures():
    fixture=contract.check_identity()
    assert len(fixture['rows'])==369
    assert sum(r['original_failure'] for r in fixture['rows'])==101
    assert contract.equal(1e-300,0.) is False


def test_every_case_is_required_by_public_report_description():
    from reproducibility.run import inventory
    keys={r['key'] for r in contract.cases()};capability='PyFLASH.report.describe_group'
    complete=next(r for r in inventory(keys) if r['capability']==capability)
    incomplete=next(r for r in inventory(keys-{next(iter(keys))}) if r['capability']==capability)
    assert complete['status']=='validated-complete-contract'
    assert incomplete['status']!='validated-complete-contract'


def test_replacing_description_answer_fails_identity(monkeypatch,tmp_path):
    fixture=json.loads(contract.FIXTURE.read_text(encoding='utf-8'));fixture['rows'][0]['expected']['n']=100
    path=tmp_path/'altered.json';path.write_text(json.dumps(fixture),encoding='utf-8');monkeypatch.setattr(contract,'FIXTURE',path)
    with pytest.raises(ValueError,match='differ from before-correction'):contract.check_identity()
