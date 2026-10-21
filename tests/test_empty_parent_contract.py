"""Empty inputs must complete without inventing observations or losing state."""
from copy import deepcopy
import shutil
import pytest
from reproducibility import empty_parent_contract as contract

CASES = contract.cases()


@pytest.fixture(scope='module', autouse=True)
def unchanged_original_empty_shapes_and_failed_adapter():
    contract.check_identity()


@pytest.mark.parametrize('item', CASES, ids=lambda item: item['key'])
def test_complete_original_empty_parent_call(item, tmp_path):
    original = deepcopy(item)
    contract.production(item, tmp_path / 'case')
    assert item == original


@pytest.mark.parametrize('name', ['original/failed-adapter.json', 'original-v2/before.json',
    'original-v2/native/empty-parent-tables-results.json'])
def test_changed_original_empty_evidence_refuses(name, tmp_path, monkeypatch):
    copied = tmp_path / 'evidence'
    shutil.copytree(contract.ARCHIVE, copied)
    path = copied / name
    path.write_bytes(path.read_bytes() + b' ')
    monkeypatch.setattr(contract, 'ARCHIVE', copied)
    with pytest.raises(ValueError):
        contract.check_identity()


@pytest.mark.parametrize('damage', ['dtype', 'phantom-row'])
def test_empty_full_table_prediction_damage_refuses(damage, tmp_path):
    item = deepcopy(CASES[0])
    if damage == 'dtype':
        item['expected']['dtypes'][0] = 'float64'
    else:
        item['expected']['rows'].append(['invented'] * len(item['expected']['columns']))
    with pytest.raises(AssertionError):
        contract.production(item, tmp_path / 'case')


def test_all_original_empty_options_are_required_without_parent_promotion():
    assert len(CASES) == len({item['key'] for item in CASES}) == 72
    assert {item['case']['kind'] for item in CASES} == {'main', 'mini', 'batch'}
    assert not contract.COMPLETE_CAPABILITIES


@pytest.mark.parametrize('name', ['amendment.json', 'accepted-reference.py'])
def test_marker_storage_amendment_changes_refuse(name, tmp_path, monkeypatch):
    copied = tmp_path / 'amendment'
    shutil.copytree(contract.AMENDMENT, copied)
    path = copied / name
    path.write_bytes(path.read_bytes() + b' ')
    monkeypatch.setattr(contract, 'AMENDMENT', copied)
    with pytest.raises(ValueError):
        contract.check_identity()
