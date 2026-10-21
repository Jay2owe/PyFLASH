"""Every preserved comparison drawing must match independently declared geometry."""
from copy import deepcopy
import json
import pytest
from reproducibility import comparison_geometry_contract as contract


@pytest.mark.parametrize('case',contract.cases(),ids=lambda row:row['key'])
def test_complete_drawing_matches_independent_geometry(case):
    original=deepcopy(case)
    assert contract.equal(contract.production(case),case['expected'])
    assert case==original


def test_original_drawings_and_reference_revisions_are_preserved():
    fixture=contract.check_identity()
    assert len(fixture['rows'])==388
    assert sum(row['original_failure'] for row in fixture['rows'])==186
    assert contract.equal(1e-300,0.) is False


def test_every_drawing_case_is_required_by_each_shared_owner():
    from reproducibility.run import inventory, _inventory_metadata, _inventory_execution_status
    keys=contract.required_keys()
    metadata=_inventory_metadata()
    frozen=deepcopy(metadata)
    def status(keys):return _inventory_execution_status(metadata,keys)
    assert inventory(keys)==status(keys)
    for capability in contract.CAPABILITIES:
        complete=next(row for row in status(keys) if row['capability']==capability)
        incomplete=next(row for row in status(keys-{next(iter(keys))}) if row['capability']==capability)
        assert complete['status']=='validated-complete-contract'
        assert incomplete['status']!='validated-complete-contract'
    assert metadata==frozen


def test_replacing_drawing_answer_fails_identity(monkeypatch,tmp_path):
    payload=json.loads(contract.FIXTURE.read_text(encoding='utf-8'))
    payload['rows'][0]['expected']={'maximum':42}
    altered=tmp_path/'altered.json';altered.write_text(json.dumps(payload),encoding='utf-8')
    monkeypatch.setattr(contract,'FIXTURE',altered)
    with pytest.raises(ValueError,match='differ from before-correction'):contract.check_identity()
