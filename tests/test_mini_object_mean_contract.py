"""Object storage cannot round integer measurements before their mean."""
from copy import deepcopy
import shutil
import pytest
from reproducibility import mini_object_mean_contract as contract

CASES = contract.cases()


@pytest.fixture(scope='module', autouse=True)
def unchanged_original_evidence():
    contract.check_identity()


@pytest.mark.parametrize('item', CASES, ids=lambda item: item['key'])
def test_full_public_summary_against_original_exact_means(item, tmp_path):
    original = deepcopy(item)
    contract.production(item, tmp_path / 'case')
    assert item == original


@pytest.mark.parametrize('name', ['original/before.json', 'object_mean_reference.py',
                                  'original/native/original-object-double-transport-results.json'])
def test_altered_original_evidence_refuses(name, tmp_path, monkeypatch):
    copied = tmp_path / 'evidence'
    shutil.copytree(contract.ARCHIVE, copied)
    path = copied / name
    path.write_bytes(path.read_bytes() + b' ')
    monkeypatch.setattr(contract, 'ARCHIVE', copied)
    with pytest.raises(ValueError):
        contract.check_identity()


@pytest.mark.parametrize('damage', ['mean', 'dtype', 'excluded'])
def test_altered_complete_prediction_refuses(damage, tmp_path):
    key = 'excluded' if damage == 'excluded' else 'integer-rounding'
    item = deepcopy(next(row for row in CASES if row['case']['key'] == key + '.direct.False'))
    if damage == 'dtype':
        item['expected']['dtypes'][1] = 'int64'
    else:
        item['expected']['rows'][0][1] = 0.
    with pytest.raises(AssertionError):
        contract.production(item, tmp_path / 'case')


def test_declared_storage_routes_do_not_certify_all_summary_options():
    assert len(CASES) == len({item['key'] for item in CASES}) == 48
    assert {item['case']['route'] for item in CASES} == {'direct', 'csv'}
    assert {item['case']['progress'] for item in CASES} == {False, True}
    assert not contract.COMPLETE_CAPABILITIES
