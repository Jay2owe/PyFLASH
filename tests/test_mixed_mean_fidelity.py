"""Mixed numeric inputs must reach averaging before lossy coercion."""
import copy
import shutil
import pytest
from reproducibility import mixed_mean_fidelity_contract as contract

CASES = contract.cases()


@pytest.fixture(scope='module', autouse=True)
def unchanged_original_inputs_and_answers():
    contract.check_identity()


@pytest.mark.parametrize('item', CASES, ids=lambda item: item['key'])
def test_actual_mixed_window_arrays_and_original_dtypes(item):
    original = copy.deepcopy(item); contract.production(item); assert item == original


@pytest.mark.parametrize('name', ['source-files.json', 'real/before.json', 'complex/before.json'])
def test_modified_original_numeric_evidence_fails(name, tmp_path, monkeypatch):
    archive = tmp_path / 'original-evidence'; shutil.copytree(contract.ARCHIVE, archive)
    path = archive / name; path.write_bytes(path.read_bytes() + b' ')
    monkeypatch.setattr(contract, 'ARCHIVE', archive)
    with pytest.raises(ValueError, match='evidence'):
        contract.check_identity()


@pytest.mark.parametrize('damage', ['value', 'dtype', 'input'])
def test_wrong_output_or_changed_caller_is_detected(damage, monkeypatch):
    from PyFLASH import utils
    original = utils.moving_average
    def broken(values, w=7):
        result = original(values, w)
        if damage == 'value': result[0] += 1
        elif damage == 'dtype': result = result.astype(complex)
        else: values[0] += 1
        return result
    monkeypatch.setattr(utils, 'moving_average', broken)
    with pytest.raises(AssertionError):
        contract.production(CASES[0])


def test_supporting_arithmetic_does_not_certify_a_parent_method():
    assert len(CASES) == 60 and not contract.COMPLETE_CAPABILITIES
