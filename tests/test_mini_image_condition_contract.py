"""Stored and returned image metadata must follow the current subject conditions."""
from copy import deepcopy
import shutil
import pytest
from reproducibility import mini_image_condition_contract as contract


@pytest.fixture(scope='module', autouse=True)
def original_evidence():
    contract.check_identity()


@pytest.mark.parametrize('item', contract.cases(), ids=lambda row: row['key'])
def test_full_acquired_image_metadata(item, tmp_path):
    contract.production(item, tmp_path / 'input')


@pytest.mark.parametrize('name', ['original/before.json', 'image_condition_reference.py',
                                   'original/native/acquired-image-conditions-results.json'])
def test_changed_original_evidence_refuses(name, tmp_path, monkeypatch):
    copied = tmp_path / 'original'
    shutil.copytree(contract.ARCHIVE, copied)
    path = copied / name
    path.write_bytes(path.read_bytes() + b' ')
    monkeypatch.setattr(contract, 'ARCHIVE', copied)
    with pytest.raises(ValueError):
        contract.check_identity()


@pytest.mark.parametrize('damage', ['condition', 'factor', 'ownership'])
def test_damaged_image_metadata_refuses(damage, tmp_path):
    item = deepcopy(contract.cases()[0])
    column = {'condition': 'Condition', 'factor': 'Treatment', 'ownership': 'AnimalName'}[damage]
    item['expected']['rows'][0][item['expected']['columns'].index(column)] = 'wrong'
    with pytest.raises(AssertionError):
        contract.production(item, tmp_path / 'input')


def test_scope_does_not_certify_other_image_layouts_or_decoding():
    assert len(contract.cases()) == 2
    assert not contract.COMPLETE_CAPABILITIES
