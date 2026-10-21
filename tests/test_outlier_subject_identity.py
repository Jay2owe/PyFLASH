"""Independently frozen identity, scope and nonmutation controls."""
import json
import pytest
from reproducibility import outlier_subject_identity_contract as contract


@pytest.mark.parametrize('case',contract.cases(),ids=lambda row:row['key'])
def test_subject_identity_and_whole_animal_scope(case,tmp_path):
    actual=contract.production(case,tmp_path)
    if actual != case['expected']:
        (tmp_path/'unresolved-observation.json').write_text(
            json.dumps(dict(case=case,actual=actual),indent=2,allow_nan=False),encoding='utf-8')
    assert actual == case['expected']


def test_frozen_expectations_reproduce_without_candidate_calls():
    import runpy
    source=runpy.run_path(str(contract.ARCHIVE/'reference-producer.py'))
    assert source['INPUT']==json.loads((contract.ARCHIVE/'input-definitions.json').read_text())
    for case in contract.cases():
        assert source['expected'](case)==case['expected']


def test_supporting_controls_do_not_claim_complete_parent_approval():
    assert not contract.COMPLETE_CAPABILITIES
    assert json.loads((contract.ARCHIVE/'declaration.json').read_text())['whole_parent_approval'] is False
