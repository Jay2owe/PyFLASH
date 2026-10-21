import copy
import shutil

import pytest

from reproducibility import whole_condition_contract as contract

CASES = contract.cases()


@pytest.fixture(scope='module', autouse=True)
def authenticate_native_originals():
    contract.check_identity()


@pytest.mark.parametrize('item', CASES, ids=lambda item: item['key'])
def test_installed_whole_parent_assigns_every_cell_and_preserves_nested_ownership(item):
    before = copy.deepcopy(item)
    contract.production(item)
    assert item == before


@pytest.mark.parametrize('name', ['source-files.json', 'original/before.json',
    'native-original/whole-parent-factor-assignment-results.json'])
def test_changed_originals_cannot_become_accepted_predictions(name, tmp_path, monkeypatch):
    archive = tmp_path / 'original-conditions'
    shutil.copytree(contract.ARCHIVE, archive)
    path = archive / name
    path.write_bytes(path.read_bytes() + b' ')
    monkeypatch.setattr(contract, 'ARCHIVE', archive)
    with pytest.raises(ValueError, match='evidence'):
        contract.check_identity()


@pytest.mark.parametrize('field', ['expected', 'raw_expected', 'images_expected'])
def test_changed_complete_prediction_is_refused(field):
    item = copy.deepcopy(next(item for item in CASES if item['case']['images'] == 'stale'))
    item['expected'][field]['rows'][0][0] = 'changed-original-answer'
    with pytest.raises(AssertionError):
        contract.production(item)


@pytest.mark.parametrize('damage', ['summary-cell', 'raw-cell', 'image-cell', 'nested-image-data'])
def test_incorrect_installed_table_or_nested_mutation_is_detected(damage, monkeypatch):
    from PyFLASH.experiment import Experiment
    method = Experiment.set_condition_list
    def damaged(self, groups):
        result = method(self, groups)
        if damage == 'summary-cell':
            self.summaries['SCN'].iloc[0, 1] += 1
        elif damage == 'raw-cell':
            self.data['0'].df.iloc[0, 1] += 1
        elif damage == 'image-cell':
            self.images.loc[0, 'Marker'] = 'changed'
        else:
            self.imagesDict['original']['paths'].append('changed')
        return result
    monkeypatch.setattr(Experiment, 'set_condition_list', damaged)
    item = next(item for item in CASES if item['case']['images'] == 'stale')
    with pytest.raises(AssertionError):
        contract.production(item)


def test_functional_assignment_does_not_certify_processing_or_mini_experiments():
    assert len(CASES) == 864
    assert len(contract.required_keys(contract.CAPABILITY)) > 864
    assert not contract.required_keys('PyFLASH.experiment.Experiment.processData')
    assert not contract.required_keys('PyFLASH.experiment.MiniExperiment.set_condition_list')
