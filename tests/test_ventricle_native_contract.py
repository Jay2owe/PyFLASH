"""Every boundary must remain attached to its original spatial group and rows."""
import copy
import shutil
import pytest
from reproducibility import ventricle_native_contract as contract

CASES = contract.cases()


@pytest.fixture(scope='module', autouse=True)
def unchanged_original_native_evidence():
    contract.check_identity()


@pytest.mark.parametrize('item', CASES, ids=lambda item: item['key'])
def test_whole_public_boundary_tables_match_native_geometry(item):
    original = copy.deepcopy(item)
    contract.production(item)
    assert item == original


def test_parent_and_direct_completion_require_their_own_full_outputs():
    assert contract.COMPLETE_CAPABILITIES == {contract.DIRECT, contract.PARENT}
    assert len(contract.required_keys(contract.DIRECT)) == 105
    assert len(contract.required_keys(contract.PARENT)) == 326
    assert contract.required_keys(contract.DIRECT).isdisjoint(contract.required_keys(contract.PARENT))
    assert contract.required_keys('PyFLASH.markers.Antibody.analyse_roi') == set()
    assert contract.required_keys('PyFLASH.experiment.Experiment.processData') == set()


@pytest.mark.parametrize('resource', ['source-manifest.json', 'native-v1/frozen.json',
                                     'native-v1/native-r/complete-ventricle-queries.json'])
def test_changed_original_boundary_evidence_cannot_pass(resource, tmp_path, monkeypatch):
    archive = tmp_path / 'archive'
    shutil.copytree(contract.ARCHIVE, archive)
    path = archive / resource
    path.write_bytes(path.read_bytes() + b' ')
    monkeypatch.setattr(contract, 'ARCHIVE', archive)
    with pytest.raises(ValueError, match='evidence'):
        contract.check_identity()


@pytest.mark.parametrize('operation', ['direct', 'parent'])
def test_changed_reference_distance_is_not_hidden_by_table_tolerance(operation):
    item = copy.deepcopy(next(item for item in CASES if item['operation'] == operation))
    item['row']['expected'][0] += 1e-7
    with pytest.raises(AssertionError):
        contract.production(item)
