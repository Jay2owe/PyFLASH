"""Declared factor labels and acquired tables retain literal ownership."""
from copy import deepcopy
import shutil
import pytest
from reproducibility import parent_ownership_contract as contract

CASES = contract.cases()


@pytest.fixture(scope='module', autouse=True)
def original_native_evidence():
    contract.check_identity()


@pytest.mark.parametrize('item', CASES, ids=lambda item: item['key'])
def test_complete_original_public_assignment_and_table_ownership(item):
    original = deepcopy(item)
    contract.production(item)
    assert item == original


@pytest.mark.parametrize('name', ['adapter-amendment.json', 'parent-conditions-original/before.json',
    'parent-conditions-original-v2/native/literal-factor-labels-results.json', 'batch-names-original/before.json'])
def test_original_evidence_change_refuses(name, tmp_path, monkeypatch):
    copied = tmp_path / 'evidence'
    shutil.copytree(contract.ARCHIVE, copied)
    path = copied / name
    path.write_bytes(path.read_bytes() + b' ')
    monkeypatch.setattr(contract, 'ARCHIVE', copied)
    with pytest.raises(ValueError):
        contract.check_identity()


@pytest.mark.parametrize('damage', ['label', 'raw-label', 'dtype', 'table-name'])
def test_changed_full_prediction_refuses(damage):
    item = deepcopy(next(item for item in CASES if item['kind'] == ('names' if damage == 'table-name' else 'labels') and item['expected']))
    if damage == 'table-name':
        item['expected'][0] = 'lost-table'
    elif damage == 'label':
        item['expected']['rows'][0][-1] = 'wrong-label'
    elif damage == 'raw-label':
        item['raw_expected']['rows'][0][-1] = 'wrong-label'
    else:
        item['expected']['dtypes'][-1] = 'float64'
    with pytest.raises(AssertionError):
        contract.production(item)


def test_bounded_assignment_and_table_helper_are_not_whole_batch_certification():
    assert len(CASES) == len({item['key'] for item in CASES}) == 328
    assert len([item for item in CASES if item['kind'] == 'labels']) == 256
    assert len([item for item in CASES if item['kind'] == 'names']) == 72
    assert not contract.COMPLETE_CAPABILITIES
