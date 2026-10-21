"""Queues retain explicit labels and every original scientific artist."""
from copy import deepcopy
import shutil
import pytest
from reproducibility import distribution_label_contract as contract
CASES = contract.originals()

@pytest.fixture(scope='module', autouse=True)
def authenticated_original_evidence():
    contract.check_identity()

@pytest.mark.parametrize('original', CASES, ids=[r['case']['key'] for r in CASES])
def test_finished_public_plot_preserves_custom_labels_and_original_artists(original, tmp_path):
    contract.production(original, tmp_path)

@pytest.mark.parametrize('resource', ['source-manifest.json', contract.ORIGINAL + '/frozen-before.json'])
def test_changed_literal_observation_is_rejected(resource, tmp_path, monkeypatch):
    copied = tmp_path / 'evidence'
    shutil.copytree(contract.ARCHIVE, copied)
    path = copied / resource
    path.write_bytes(path.read_bytes() + b' ')
    monkeypatch.setattr(contract, 'ARCHIVE', copied)
    with pytest.raises(ValueError): contract.check_identity()

@pytest.mark.parametrize('damage', ['label', 'missing-artist', 'scientific-height'])
def test_damaged_label_or_artist_is_rejected(damage, tmp_path):
    original = next(r for r in CASES if r['case']['key'] == 'plot_histograms.single.User-unit')
    actual = contract.production(original, tmp_path)
    broken = deepcopy(actual)
    if damage == 'label': broken['records'][0]['xlabel'] = 'A User unit'
    elif damage == 'missing-artist': broken['records'][0]['patches'].pop()
    else: broken['records'][0]['patches'][0]['bounds'][-1] += 1
    with pytest.raises(AssertionError): contract.check_result(original, broken)
