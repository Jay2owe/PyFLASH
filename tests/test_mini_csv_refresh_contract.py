"""A refresh must not retain retired tables or publish partially read inputs."""
from copy import deepcopy
import shutil
import pytest
from reproducibility import mini_csv_refresh_contract as contract

CASES = contract.cases()


@pytest.fixture(scope='module', autouse=True)
def unchanged_original_and_failed_candidate_evidence():
    contract.check_identity()


@pytest.mark.parametrize('item', CASES, ids=lambda item: item['key'])
def test_native_full_refresh_and_atomic_refusal(item, tmp_path):
    original = deepcopy(item)
    contract.production(item, tmp_path / 'case')
    assert item == original


@pytest.mark.parametrize('name', ['csv-refresh-original/before.json', 'adapter-amendment.json',
    'csv-refresh-original-v2/native/csv-refresh-fields-results.json'])
def test_original_trial_and_native_evidence_changes_refuse(name, tmp_path, monkeypatch):
    copied = tmp_path / 'evidence'
    shutil.copytree(contract.ARCHIVE, copied)
    path = copied / name
    path.write_bytes(path.read_bytes() + b' ')
    monkeypatch.setattr(contract, 'ARCHIVE', copied)
    with pytest.raises(ValueError):
        contract.check_identity()


@pytest.mark.parametrize('damage', ['measurement', 'subject', 'dtype', 'missing-table'])
def test_damaged_full_refresh_prediction_refuses(damage, tmp_path):
    item = deepcopy(next(item for item in CASES if item['case']['mode'] == 'replace'))
    frame = item['expected']['Data']
    if damage == 'measurement':
        frame['rows'][0][1] += 1.
    elif damage == 'subject':
        frame['rows'][0][0] = 'wrong-subject'
    elif damage == 'dtype':
        frame['dtypes'][1] = 'object'
    else:
        del item['expected']['Data']
    with pytest.raises(AssertionError):
        contract.production(item, tmp_path / 'case')


def test_every_original_transition_is_required_without_whole_import_certification():
    assert len(CASES) == len({item['key'] for item in CASES}) == 32
    assert {item['case']['mode'] for item in CASES} == {
        'replace', 'add', 'remove', 'rename', 'empty', 'invalid-last', 'invalid-first', 'header-only'}
    assert {item['case']['labels'] for item in CASES} == {False, True}
    assert {item['case']['progress'] for item in CASES} == {False, True}
    assert not contract.COMPLETE_CAPABILITIES
