"""All correction coordinates and decisions remain aligned in complete records."""
from copy import deepcopy
import json
import pytest
from reproducibility import comparison_record_audit_contract as contract


@pytest.mark.parametrize('case',contract.cases(),ids=lambda row:row['key'])
def test_full_audit_record_matches_independent_accepted_correction_schema(case):
    original=deepcopy(case)
    assert contract.equal(contract.production(case),case['expected'])
    assert case==original


def test_before_correction_record_inputs_and_native_coordinates_remain_preserved():
    fixture=contract.check_identity()
    assert len(fixture['rows'])==3096
    assert sum(r['original_failure'] for r in fixture['rows'])==0
    assert len(contract.required_keys())==3672


def test_both_audited_and_unaudited_cases_are_required_by_record_builder():
    from reproducibility.run import inventory
    keys=contract.required_keys();capability='PyFLASH.report.build_comparison_record'
    complete=next(r for r in inventory(keys) if r['capability']==capability)
    incomplete=next(r for r in inventory(keys-{next(iter(keys))}) if r['capability']==capability)
    assert complete['status']=='validated-complete-contract'
    assert incomplete['status']!='validated-complete-contract'


def test_changing_one_correction_coordinate_fails_identity(monkeypatch,tmp_path):
    fixture=json.loads(contract.FIXTURE.read_text(encoding='utf-8'));fixture['rows'][0]['parameters']['correction_audit']['holm'][0]=.9
    path=tmp_path/'altered.json';path.write_text(json.dumps(fixture),encoding='utf-8');monkeypatch.setattr(contract,'FIXTURE',path)
    with pytest.raises(ValueError,match='differ from before-correction'):contract.check_identity()
