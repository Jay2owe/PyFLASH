"""Complete calibrated-area tables preserve measurements and normalized counts."""
import copy
import shutil
import pytest
from reproducibility import summary_area_contract as contract

CASES = contract.cases()


@pytest.fixture(scope='module', autouse=True)
def unchanged_native_area_evidence():
    contract.check_identity()


@pytest.mark.parametrize('item', CASES, ids=lambda item: item['key'])
def test_full_native_summary_table_matches_imagej_and_independent_r(item):
    original = copy.deepcopy(item)
    contract.production(item)
    assert item == original


def test_limited_area_routes_do_not_certify_the_whole_summary_method():
    assert len(CASES) == 384
    assert contract.COMPLETE_CAPABILITIES == set()


@pytest.mark.parametrize('resource', ['source-manifest.json', 'native-imagej-v1/receipt.json', 'native-r/frozen.json'])
def test_changed_independent_area_evidence_is_refused(resource, tmp_path, monkeypatch):
    archive = tmp_path / 'archive'
    shutil.copytree(contract.ARCHIVE, archive)
    path = archive / resource
    path.write_bytes(path.read_bytes() + b' ')
    monkeypatch.setattr(contract, 'ARCHIVE', archive)
    with pytest.raises(ValueError, match='evidence'):
        contract.check_identity()


@pytest.mark.parametrize('position', [0, 1, 3, 4])
def test_damaged_count_area_or_volume_cannot_be_hidden(position):
    item = copy.deepcopy(CASES[0])
    item['expected'][position] += .01
    with pytest.raises(AssertionError):
        contract.production(item)


@pytest.mark.parametrize('density', [0., -1., float('nan'), float('inf'), 1j])
def test_invalid_pixel_density_is_refused_by_the_existing_unit_owner(density):
    item = copy.deepcopy(CASES[0])
    item['case']['native']['density'] = density
    with pytest.raises((TypeError, ValueError)):
        contract.production(item)


def test_existing_positive_real_scalar_calibration_policy_is_preserved():
    # The shared converter already accepts True as the exact positive real 1.
    # The area route must preserve that policy rather than add its own parser.
    item = copy.deepcopy(CASES[0])
    item['case']['native']['density'] = True
    contract.production(item)
