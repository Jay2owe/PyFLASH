"""Whole flat-table lifecycle checks retain every scientific and metadata cell."""
from copy import deepcopy
import shutil
import pytest
from reproducibility import mini_lifecycle_contract as contract

CASES = contract.cases()


@pytest.fixture(scope='module', autouse=True)
def original_evidence():
    contract.check_identity()


@pytest.mark.parametrize('item', CASES, ids=[row['key'] for row in CASES])
def test_complete_public_lifecycle(item, tmp_path):
    contract.production(item, tmp_path / 'input')


@pytest.mark.parametrize('name', ['lifecycle-original/before.json', 'lifecycle_reference.py',
                                   'lifecycle-original/native/flat-csv-lifecycle-results.json'])
def test_changed_original_evidence_refuses(name, tmp_path, monkeypatch):
    copied = tmp_path / 'original'
    shutil.copytree(contract.ARCHIVE, copied)
    path = copied / name
    path.write_bytes(path.read_bytes() + b' ')
    monkeypatch.setattr(contract, 'ARCHIVE', copied)
    with pytest.raises(ValueError):
        contract.check_identity()


@pytest.mark.parametrize('damage', ['mean', 'factor', 'raw-condition', 'dtype'])
def test_damaged_lifecycle_prediction_refuses(damage, tmp_path):
    item = deepcopy(CASES[0])
    if damage == 'dtype':
        item['expected']['dtypes'][1] = 'int64'
    elif damage == 'raw-condition':
        item['raw_expected']['Data1']['rows'][0][-1] = 'wrong'
    else:
        item['expected']['rows'][0][1 if damage == 'mean' else 2] = 99.
    with pytest.raises(AssertionError):
        contract.production(item, tmp_path / 'input')


def test_scope_covers_every_declared_table_and_process_option():
    tables = [row for row in CASES if row['kind'] == 'table']
    assert len(tables) == 128
    assert len({row['key'] for row in CASES}) == len(CASES) == 134
    for option in ('progress', 'images', 'codes'):
        assert {row['case'][option] for row in tables} == {False, True}
    assert {row['case']['tables'] for row in tables} == {1, 2, 3, 4}
    assert {row['case']['route'] for row in tables} == {'steps', 'process'}
    assert not contract.COMPLETE_CAPABILITIES
