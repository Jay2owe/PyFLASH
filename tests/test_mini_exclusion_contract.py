"""Excluded measurements must not become metadata or alter original inputs."""
from copy import deepcopy
import shutil
import pytest
from reproducibility import mini_exclusion_contract as contract

CASES = contract.cases()


@pytest.fixture(scope='module', autouse=True)
def original_evidence():
    contract.check_identity()


@pytest.mark.parametrize('item', CASES, ids=[row['key'] for row in CASES])
def test_complete_public_tables(item):
    contract.production(item)


@pytest.mark.parametrize('name', ['original/before.json', 'exclusion_reference.py',
                                   'original/native/excluded-measurement-means-results.json'])
def test_changed_original_evidence_refuses(name, tmp_path, monkeypatch):
    copied = tmp_path / 'original'
    shutil.copytree(contract.ARCHIVE, copied)
    path = copied / name
    path.write_bytes(path.read_bytes() + b' ')
    monkeypatch.setattr(contract, 'ARCHIVE', copied)
    with pytest.raises(ValueError):
        contract.check_identity()


@pytest.mark.parametrize('damage', ['mean', 'excluded', 'factor', 'dtype'])
def test_damaged_table_prediction_refuses(damage):
    key = 'excluded' if damage == 'excluded' else 'middle'
    item = deepcopy(next(row for row in CASES if row['case']['key'] == key + '.object.False'))
    if damage in {'mean', 'excluded'}:
        item['expected']['rows'][0][1] = 0.
    elif damage == 'factor':
        item['expected']['rows'][0][2] = '1'
    else:
        item['expected']['dtypes'][1] = 'int64'
    with pytest.raises(AssertionError):
        contract.production(item)


def test_scope_includes_every_original_case_without_certifying_other_summary_routes():
    assert len(CASES) == 96
    assert len({row['key'] for row in CASES}) == 96
    assert {row['case']['metadata'] for row in CASES} == {'object', 'string', 'category', 'datetime'}
    assert {row['case']['progress'] for row in CASES} == {False, True}
    assert not contract.COMPLETE_CAPABILITIES
