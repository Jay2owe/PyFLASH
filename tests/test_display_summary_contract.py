"""Public display copies preserve all measurements and original caller state."""
from copy import deepcopy
import shutil
import pytest
from reproducibility import display_summary_contract as contract

CASES = contract.cases()


@pytest.fixture(scope='module', autouse=True)
def original_literal_display_evidence():
    contract.check_identity()


@pytest.mark.parametrize('item', CASES, ids=lambda item: item['key'])
def test_complete_public_display_getter(item):
    original = deepcopy(item)
    contract.production(item)
    assert item == original


@pytest.mark.parametrize('name', ['before.json', 'original-0-display_summary_whole_reference_20261008.py',
                                  'original-3-export.py'])
def test_changed_original_display_evidence_refuses(name, tmp_path, monkeypatch):
    copied = tmp_path / 'evidence'
    shutil.copytree(contract.ARCHIVE, copied)
    path = copied / name
    path.write_bytes(path.read_bytes() + b' ')
    monkeypatch.setattr(contract, 'ARCHIVE', copied)
    with pytest.raises(ValueError):
        contract.check_identity()


@pytest.mark.parametrize('damage', ['label', 'measurement', 'dtype'])
def test_changed_full_display_prediction_refuses(damage):
    item = deepcopy(CASES[0])
    if damage == 'label': item['expected']['columns'][0] = 'wrong label'
    elif damage == 'measurement': item['expected']['rows'][0][2] = 999
    else: item['expected']['dtypes'][2] = 'float64'
    with pytest.raises(AssertionError):
        contract.production(item)


@pytest.mark.parametrize('damage', ['original-owner', 'source-cell', 'attributes'])
def test_correct_values_cannot_hide_changed_source_or_lost_metadata(damage, monkeypatch):
    from PyFLASH.experiment import Experiment
    original = Experiment.getDisplaySummary
    def broken(self, roi_base=None):
        actual = original(self, roi_base)
        source = self.summaries['SCN']
        if damage == 'original-owner':
            source.columns = actual.columns
            return source
        if damage == 'source-cell': source.iloc[0, 0] = 'changed source'
        else: actual.attrs = {}
        return actual
    monkeypatch.setattr(Experiment, 'getDisplaySummary', broken)
    with pytest.raises(AssertionError):
        contract.production(CASES[0])


def test_only_the_literal_display_getters_receive_complete_functional_coverage():
    assert len(CASES) == len({item['key'] for item in CASES}) == 240
    assert {item['case']['owner'] for item in CASES} == {'Experiment', 'MiniExperiment', 'Batch'}
    for capability in contract.COMPLETE_CAPABILITIES:
        assert len(contract.required_keys(capability)) == 80
    assert not contract.required_keys('PyFLASH.experiment.Experiment.createSummary')
