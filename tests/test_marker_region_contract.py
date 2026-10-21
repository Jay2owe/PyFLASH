"""Public selected-region curves against immutable native scientific inputs."""
from copy import deepcopy
import shutil
import pytest
from reproducibility import marker_region_contract as contract
CASES = contract.cases()


@pytest.fixture(scope='module', autouse=True)
def accepted_native_evidence(tmp_path_factory):
    contract.check_identity()
    contract.check_native_references(tmp_path_factory.mktemp('marker-region-r'))


@pytest.mark.parametrize('item', CASES, ids=[item['key'] for item in CASES])
def test_actual_public_selected_regions_groups_and_full_curves(item, tmp_path):
    contract.production(item, tmp_path)


@pytest.mark.parametrize('resource', ['source-manifest.json',
    contract.ORIGINAL + '/original-objects.json',
    contract.ORIGINAL + '/native-r/marker-region-distributions-results.json',
    contract.SCIPY + '/native-scipy-original-selected-inputs.json'])
def test_changed_original_evidence_is_rejected(resource, tmp_path, monkeypatch):
    copied = tmp_path / 'evidence';shutil.copytree(contract.ARCHIVE, copied)
    path = copied / resource;path.write_bytes(path.read_bytes() + b' ')
    monkeypatch.setattr(contract, 'ARCHIVE', copied)
    with pytest.raises(ValueError, match='evidence'): contract.check_identity()


@pytest.mark.parametrize('damage', ['wrong-region', 'leaked-measurement', 'wrong-step', 'wrong-count', 'lost-unit'])
def test_damaged_public_scientific_outputs_are_rejected(damage, tmp_path):
    item = next(item for item in CASES if item['key'] == 'ecdf-regions.SCN.conditions.proportion.ordinary')
    actual, _ = contract.production(item, tmp_path)
    broken = deepcopy(actual)
    if damage == 'wrong-region': broken['records'][0]['roi'] = 'OC'
    elif damage == 'leaked-measurement': broken['records'][0]['lines'][0]['x'][1] = 100.
    elif damage == 'wrong-step': broken['records'][0]['lines'][0]['y'][1] = .1
    elif damage == 'wrong-count': broken['returned']['n'][0] = 6
    else: broken['records'][0]['xlabel'] = 'Volume'
    with pytest.raises(AssertionError): contract.check_result(item, broken)


def test_empty_group_cannot_gain_a_scientific_line(tmp_path):
    item = next(item for item in CASES if item['key'] == 'ecdf-regions.SCN.conditions.proportion.ordinary')
    actual, _ = contract.production(item, tmp_path)
    broken = deepcopy(actual);broken['records'][-1]['lines'] = deepcopy(broken['records'][0]['lines'])
    with pytest.raises(AssertionError): contract.check_result(item, broken)
