"""Actual native/nullable public summaries retain extreme and integer means."""
import copy
import shutil
import pytest
from reproducibility import mini_scientific_contract as contract

CASES = [item for item in contract.cases() if item['kind'] in ('typed', 'integer', 'integer-boundary')]

@pytest.fixture(scope='module', autouse=True)
def unchanged_independent_storage_evidence():
    contract.check_identity()

@pytest.mark.parametrize('item', CASES, ids=lambda item: item['key'])
def test_public_summary_storage_against_independent_frozen_means(item):
    original = copy.deepcopy(item)
    contract.production(item)
    assert item == original

def test_every_recorded_dtype_and_progress_route_is_required_but_not_whole_certified():
    assert len(CASES) == 738
    assert {item['progress'] for item in CASES} == {False, True}
    assert {item['dtype'] for item in CASES} == {
        'float32', 'Float32', 'float64', 'Float64', 'int64', 'Int64',
        'uint64', 'UInt64', 'bool', 'boolean'}
    assert not contract.COMPLETE_CAPABILITIES

@pytest.mark.parametrize('resource', ['source-files.json', 'typed-v2/before.json', 'integers-boundary/before.json'])
def test_changed_original_storage_evidence_is_refused(resource, tmp_path, monkeypatch):
    archive = tmp_path / 'typed'
    shutil.copytree(contract.ARCHIVE / 'typed', archive)
    path = archive / resource
    path.write_bytes(path.read_bytes() + b' ')
    from reproducibility.evidence_identity import verify_manifest
    with pytest.raises(ValueError, match='evidence'):
        verify_manifest(archive, 'source-files.json', contract.TYPED_FILES_SHA256)

@pytest.mark.parametrize('damage', ['mean', 'dtype', 'missing-mask'])
def test_damaged_stored_mean_dtype_or_missingness_fails(damage):
    item = copy.deepcopy(CASES[0])
    if damage == 'mean':
        item['expected']['rows'][0][1] += 1
    elif damage == 'dtype':
        item['expected']['dtypes'][1] = 'object'
    else:
        item['expected']['rows'][0][1] = 'NaN'
    with pytest.raises(AssertionError):
        contract.production(item)
