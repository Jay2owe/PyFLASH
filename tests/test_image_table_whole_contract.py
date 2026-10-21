"""Freeze complete getters and refuse altered evidence, values or ownership."""
import copy
import json
from pathlib import Path
import shutil

import pytest
from reproducibility import image_table_contract as contract


@pytest.mark.parametrize('item', contract.cases(), ids=lambda item: item['key'])
def test_whole_image_table_matches_retained_complete_prediction(item, tmp_path):
    contract.production(item, tmp_path / 'actual')


def test_original_failures_and_current_candidate_remain_authenticated():
    contract.check_identity()


@pytest.mark.parametrize('damage', ['manifest', 'prediction', 'missing-source'])
def test_altered_original_evidence_cannot_pass(damage, tmp_path, monkeypatch):
    archive = tmp_path / 'archive'
    shutil.copytree(contract.ARCHIVE, archive)
    if damage == 'manifest':
        with (archive / 'source-files.json').open('a') as stream:
            stream.write(' ')
    elif damage == 'prediction':
        path = archive / 'original/before.json'
        data = json.loads(path.read_text())
        data['rows'][0]['expected']['columns'].append('not acquired')
        path.write_text(json.dumps(data))
    else:
        (archive / 'original/original-0-experiment.py').unlink()
    monkeypatch.setattr(contract, 'ARCHIVE', archive)
    with pytest.raises((ValueError, AssertionError)):
        contract.check_identity()


@pytest.mark.parametrize('damage', ['value', 'dtype', 'attribute'])
def test_altered_predicted_output_cannot_replace_original(damage, tmp_path):
    item = next(row for row in contract.cases() if row['group'] == 'original'
        and row['case']['owner'] == 'Experiment' and row['case']['profile'] == 'object'
        and row['case']['image_state'] == 'cached' and row['case']['option'] is True)
    if damage == 'value':
        item['expected']['rows'][0][0] = 'wrong-experiment'
    elif damage == 'dtype':
        item['expected']['dtypes'][0] = 'string'
    else:
        item['expected']['attrs'].clear()
    with pytest.raises(AssertionError):
        contract.production(item, tmp_path / 'actual')


@pytest.mark.parametrize('damage', ['value', 'attribute', 'nested-ownership'])
def test_damaged_actual_getter_cannot_pass(damage, tmp_path, monkeypatch):
    from PyFLASH.experiment import Experiment
    method = Experiment.getImageTable
    def damaged(self, *args, **kwargs):
        result = method(self, *args, **kwargs)
        if damage == 'value':
            result.iloc[0, result.columns.get_loc('Marker')] = 'wrong-marker'
        elif damage == 'attribute':
            result.attrs.clear()
        else:
            self.imagesDict['retained']['paths'].append('caller-owned-state-was-mutated')
        return result
    monkeypatch.setattr(Experiment, 'getImageTable', damaged)
    item = next(row for row in contract.cases() if row['group'] == 'original'
        and row['case']['owner'] == 'Experiment' and row['case']['profile'] == 'object'
        and row['case']['image_state'] == 'cached' and row['case']['option'] is True)
    with pytest.raises(AssertionError):
        contract.production(item, tmp_path / 'actual')


def test_getter_obligations_are_separate_from_parent_processing():
    assert len(contract.cases()) == 684
    assert len({row['key'] for row in contract.cases()}) == 684
    for capability in contract.CAPABILITIES:
        assert len(contract.required_keys(capability)) == 228
    assert not contract.required_keys('PyFLASH.experiment.Experiment.processData')
    assert not contract.required_keys('PyFLASH.batch.Batch.importImages')


def test_retained_predictions_and_nested_case_inputs_are_caller_owned():
    before = contract.cases()
    changed = contract.cases()
    changed[0]['expected']['columns'].clear()
    changed[0]['case']['owner'] = 'wrong-owner'
    assert contract.cases() == before


def test_inventory_requires_every_getter_obligation_without_promoting_processing():
    from reproducibility.run import inventory
    keys={row['key'] for row in contract.cases()}
    rows={row['capability']:row for row in inventory(keys)}
    for capability in contract.CAPABILITIES:
        assert rows[capability]['status']=='validated-complete-contract'
        assert rows[capability]['kind']=='functional-image-table-retrieval-refresh-and-ownership'
    removed=next(key for key in keys if '.Experiment.' in key)
    partial={row['capability']:row for row in inventory(keys-{removed})}
    assert partial['PyFLASH.experiment.Experiment.getImageTable']['status']!='validated-complete-contract'
    assert rows['PyFLASH.experiment.Experiment.processData']['status']!='validated-complete-contract'
