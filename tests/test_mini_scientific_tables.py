"""Permanent public table comparisons, with distinct identities and extreme means."""
import copy
import shutil
import pytest
from reproducibility import mini_scientific_contract as contract

CASES = [item for item in contract.cases() if item['kind'] in ('mean', 'identity', 'experiment-mean')]

@pytest.fixture(scope='module', autouse=True)
def unchanged_independent_evidence():
    contract.check_identity()

@pytest.mark.parametrize('item', CASES, ids=lambda item: item['key'])
def test_complete_recorded_mini_table_against_original_references(item):
    original = copy.deepcopy(item)
    contract.production(item)
    assert item == original

def test_recorded_routes_do_not_certify_unchecked_whole_methods():
    assert len(CASES) == 288
    assert not contract.COMPLETE_CAPABILITIES

@pytest.mark.parametrize('resource', ['source-files.json', 'means/frozen.json', 'identifiers/qualified-v3.json'])
def test_changed_independent_evidence_is_refused(resource, tmp_path, monkeypatch):
    archive = tmp_path / 'archive'
    shutil.copytree(contract.ARCHIVE, archive)
    path = archive / resource
    path.write_bytes(path.read_bytes() + b' ')
    monkeypatch.setattr(contract, 'ARCHIVE', archive)
    with pytest.raises(ValueError, match='evidence'):
        contract.check_identity()

@pytest.mark.parametrize('damage', ['mean', 'identity', 'source-index'])
def test_changed_numeric_identity_or_index_answer_is_detected(damage):
    kind = 'mean' if damage == 'mean' else 'identity'
    item = copy.deepcopy(next(row for row in CASES if row['kind'] == kind))
    if damage == 'mean':
        item['expected']['rows'][0][1] += 1
    elif damage == 'identity':
        item['expected']['rows'][0][0] = 'DifferentSubject'
    else:
        item['expected']['index'][0] += 1
    with pytest.raises(AssertionError):
        contract.production(item)
