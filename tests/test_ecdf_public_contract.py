"""Actual public distribution calls against preserved native scientific answers."""
from copy import deepcopy
import shutil
import pytest
from reproducibility import ecdf_public_contract as contract

CASES = contract.cases()


@pytest.fixture(scope='module', autouse=True)
def accepted_evidence_and_native_runtime(tmp_path_factory):
    contract.check_identity()
    contract.check_native_references(tmp_path_factory.mktemp('ecdf-native'))


@pytest.mark.parametrize('item', CASES, ids=[row['key'] for row in CASES])
def test_actual_public_distribution_coordinates_counts_and_labels(item, tmp_path):
    contract.production(item, tmp_path)


@pytest.mark.parametrize('resource', [
    'source-manifest.json',
    'ecdf-native-original-inputs-20261007-v1/native-r/ecdf-native-results.json',
    'ecdf-public-native-before-20261007-v1/cases.json',
])
def test_changed_accepted_evidence_is_rejected(resource, tmp_path, monkeypatch):
    copied = tmp_path / 'evidence'
    shutil.copytree(contract.ARCHIVE, copied)
    target = copied / resource
    target.write_bytes(target.read_bytes() + b' ')
    monkeypatch.setattr(contract, 'ARCHIVE', copied)
    with pytest.raises(ValueError, match='evidence'):
        contract.check_identity()


@pytest.mark.parametrize('damage', ['step-x', 'step-y', 'count', 'unit-label'])
def test_damaged_scientific_output_is_rejected(damage, tmp_path):
    item = next(row for row in CASES if row['key'] == 'ecdf-public.native.nonfinite.proportion.ordinary')
    actual, _ = contract.production(item, tmp_path)
    broken = deepcopy(actual)
    if damage == 'step-x':
        broken['records'][0]['lines'][0]['x'][1] = 99.
    elif damage == 'step-y':
        broken['records'][0]['lines'][0]['y'][1] = .5
    elif damage == 'count':
        broken['returned']['n'] = [5]
    else:
        broken['records'][0]['xlabel'] = 'Volume'
    with pytest.raises(AssertionError):
        contract.check_result(item, broken)


def test_all_infinite_measurements_cannot_report_plotted_observations(tmp_path):
    item = next(row for row in CASES if row['key'] == 'ecdf-public.native.all-infinite.count.ordinary')
    actual, _ = contract.production(item, tmp_path)
    broken = deepcopy(actual)
    broken['returned']['n'] = [3]
    with pytest.raises(AssertionError):
        contract.check_result(item, broken)


def test_lost_custom_queue_label_is_rejected(tmp_path):
    item = next(row for row in CASES if row['kind'] == 'labels' and 'single' not in row['key'])
    actual, _ = contract.production(item, tmp_path)
    broken = deepcopy(actual)
    broken['records'][0]['xlabel'] = 'A Volume'
    with pytest.raises(AssertionError):
        contract.check_result(item, broken)


def test_public_plot_preserves_original_caller_measurements(tmp_path):
    from types import SimpleNamespace
    import numpy as np
    import pandas as pd
    from PyFLASH import from_dataframe, ConditionBuilder, plotting
    frame = pd.DataFrame({'AnimalName': ['one', 'two', 'three', 'four', 'five'],
                          'Diagnosis': ['Control'] * 5,
                          'A_Volume': [-np.inf, -1., 0., 2., np.inf]})
    original_frame = frame.copy(deep=True)
    experiment = from_dataframe(frame, conditions=ConditionBuilder('Diagnosis').add('Control').build(),
                                name='ownership', condition_col='Diagnosis', animal_col='AnimalName',
                                fig_path=tmp_path / 'unsaved', data_path=tmp_path / 'data')
    experiment.data['A'] = SimpleNamespace(df=experiment.summary.copy(deep=True))
    original_summary = experiment.summary.copy(deep=True)
    original_marker = experiment.data['A'].df.copy(deep=True)
    assert plotting.plot_ecdf(experiment, 'A', 'Volume', save=False)['n'] == [3]
    pd.testing.assert_frame_equal(frame, original_frame)
    pd.testing.assert_frame_equal(experiment.summary, original_summary)
    pd.testing.assert_frame_equal(experiment.data['A'].df, original_marker)
    assert not any(path.is_file() for path in tmp_path.rglob('*'))
