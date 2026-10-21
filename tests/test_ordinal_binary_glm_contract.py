import importlib.util
import shutil
import pytest
from reproducibility import ordinal_binary_glm_contract as contract

@pytest.fixture(scope='module', autouse=True)
def authentic_native_binary_fits():
    contract.check_identity()

@pytest.mark.parametrize('row', contract.cases(), ids=lambda row: row['key'])
def test_actual_binary_fitted_state_and_complete_responses_against_native_R(row):
    assert contract.agrees(row, contract.production(row))

@pytest.mark.parametrize('name', [
    'source-manifest.json',
    'ordinal-binary-glm-before-20261007-v2/native/binomial-glm-results.json',
])
def test_changed_native_binary_evidence_refuses_before_fitting(tmp_path, monkeypatch, name):
    spec = importlib.util.spec_from_file_location('isolated_binary_evidence', contract.__file__)
    isolated = importlib.util.module_from_spec(spec); spec.loader.exec_module(isolated)
    archive = tmp_path / 'archive'; shutil.copytree(contract.ARCHIVE, archive)
    target = archive / name; target.write_bytes(target.read_bytes() + b'\n')
    isolated.ARCHIVE = archive
    monkeypatch.setattr(isolated, 'production', lambda *_: pytest.fail('Changed evidence reached fit'))
    with pytest.raises(ValueError, match='evidence'):
        isolated.validate(tmp_path / 'output')

@pytest.mark.parametrize('field', ['coefficients', 'heldout_probabilities'])
def test_changed_fitted_coefficient_or_full_response_array_fails_native_contract(field):
    row = contract.cases()[0]
    actual = contract.production(row)
    if field == 'coefficients':
        actual[field][0] += 1e-5
    else:
        actual[field][0][0] += 1e-5
    assert not contract.agrees(row, actual)
