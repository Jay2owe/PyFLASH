"""Moved scientific projects retain measurements, edits and usable input paths."""
from pathlib import Path
import pickle
import shutil
import subprocess
import sys

import pandas as pd
import pytest

from PyFLASH.experiment import MiniExperiment
from PyFLASH.serialization import load_state, save_state, STATE_SCHEMA_VERSION


def example(root):
    root.mkdir()
    raw = root / 'Signal.csv'
    raw.write_text('AnimalName,Signal\nA01,1.25\nB01,3.5\n')
    experiment = MiniExperiment('portable', str(root))
    experiment.processData(import_images=False, progress=False)
    experiment.source_paths = [str(raw)]
    experiment.images = pd.DataFrame({'AnimalName': ['A01'], 'ImageName': ['Signal'],
                                     'ImagePath': [str(root / 'image.png')]})
    experiment.representative_images = pd.DataFrame({'AnimalName': ['A01'],
        'ImagePath': [str(root / 'image.png')], 'Representative': [True], 'Manual score': [1.23456789]})
    experiment.manual_note = 'keep this edit'
    return experiment


def test_portable_save_stores_relative_paths_without_editing_live_object(tmp_path):
    root = tmp_path / 'project'
    experiment = example(root)
    filename = root / 'Results' / 'portable.pkl'
    image_before = experiment.images.copy(deep=True)
    save_state(experiment, filename, verbose=False)
    pd.testing.assert_frame_equal(experiment.images, image_before)
    assert experiment.filePath == str(root)
    stored = pickle.loads(filename.read_bytes())
    assert stored.filePath == '.'
    assert stored.source_paths == ['Signal.csv']
    assert stored.images.ImagePath.tolist() == ['image.png']
    assert stored.representative_images.ImagePath.tolist() == ['image.png']
    assert stored._state_schema_version == STATE_SCHEMA_VERSION
    assert stored._state_inputs[0]['path'] == 'Signal.csv'
    assert len(stored._state_inputs[0]['sha256']) == 64
    assert stored._state_environment['versions']['numpy']


def test_moved_project_uses_new_paths_even_when_original_still_exists(tmp_path):
    original = tmp_path / 'project'
    experiment = example(original)
    filename = original / 'Results' / 'portable.pkl'
    save_state(experiment, filename, verbose=False)
    moved = tmp_path / 'moved'
    shutil.copytree(original, moved)
    restored = load_state(moved / 'Results' / 'portable.pkl', verbose=False)
    assert restored.filePath == str(moved)
    assert restored.source_root == str(moved)
    assert restored.source_paths == [str(moved / 'Signal.csv')]
    assert restored.images.ImagePath.tolist() == [str(moved / 'image.png')]
    assert restored.representative_images.ImagePath.tolist() == [str(moved / 'image.png')]
    assert restored.representative_images['Manual score'].tolist() == [1.23456789]
    assert restored.manual_note == experiment.manual_note
    pd.testing.assert_frame_equal(restored.summary, experiment.summary)
    pd.testing.assert_frame_equal(restored.data['Signal'].df, experiment.data['Signal'].df)
    assert restored.data['Signal'].experiment is restored
    assert str(moved) in restored.csv_path


def test_external_sources_keep_their_full_paths(tmp_path):
    root = tmp_path / 'project'
    experiment = example(root)
    external = tmp_path / 'external.csv'
    external.write_text('external input')
    experiment.source_paths.append(str(external))
    filename = root / 'state.pkl'
    save_state(experiment, filename, verbose=False)
    assert pickle.loads(filename.read_bytes()).source_paths[-1] == str(external)
    assert load_state(filename, verbose=False).source_paths[-1] == str(external)


def test_previous_version_migrates_in_order_without_rewriting(tmp_path):
    experiment = example(tmp_path / 'project')
    experiment._state_schema_version = 1
    filename = tmp_path / 'previous.pkl'
    filename.write_bytes(pickle.dumps(experiment))
    before = filename.read_bytes()
    restored = load_state(filename, verbose=False)
    assert restored._state_schema_version == STATE_SCHEMA_VERSION
    assert filename.read_bytes() == before


def test_moved_analysis_reopens_in_a_fresh_process(tmp_path):
    original = tmp_path / 'project'
    experiment = example(original)
    save_state(experiment, original / 'state.pkl', verbose=False)
    moved = tmp_path / 'moved'
    shutil.copytree(original, moved)
    script = f'''
from PyFLASH.serialization import load_state
from pathlib import Path
state = load_state({str(moved / 'state.pkl')!r}, verbose=False)
assert state.filePath == {str(moved)!r}
assert state.manual_note == 'keep this edit'
assert state.source_paths == [{str(moved / 'Signal.csv')!r}]
assert state.data['Signal'].experiment is state
assert Path(state._state_inputs[0]['path']).is_file()
'''
    from reproducibility.run import python_command
    completed = subprocess.run([*python_command(), '-c', script], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_replaced_image_header_is_read_again_even_with_same_timestamp(tmp_path):
    import os
    from PIL import Image
    from PyFLASH.image_io import get_image_shape
    path = tmp_path / 'image.bmp'
    Image.new('L', (4, 6)).save(path)
    assert get_image_shape(path) == (6, 4)
    stat = path.stat()
    Image.new('L', (8, 3)).save(path)
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert get_image_shape(path) == (3, 8)


def test_moved_dataframe_analysis_restores_paths_and_plot_edits(tmp_path):
    from PyFLASH import from_dataframe
    original = tmp_path / 'dataframe-project'
    original.mkdir()
    source = original / 'subjects.csv'
    source.write_text('AnimalName,Condition,Signal\nA01,A,1.25\nB01,B,3.5\n')
    state = from_dataframe(pd.read_csv(source), group_col='Condition', subject_col='AnimalName',
                           file_path=str(original), source_paths=[str(source)])
    state.condition_list[0].label = 'Edited label'
    state.condition_list[0].color = '#123456'
    state._ui_initial_catalogue = ('rebuildable',)
    save_state(state, original / 'state.pkl', verbose=False)
    moved = tmp_path / 'moved-dataframe'
    shutil.copytree(original, moved)
    restored = load_state(moved / 'state.pkl', verbose=False)
    assert restored.filePath == str(moved)
    assert restored.fig_path == str(moved / 'Results' / 'Python Figures')
    assert restored.condition_list[0].label == 'Edited label'
    assert restored.condition_list[0].color == '#123456'
    assert not hasattr(restored, '_ui_initial_catalogue')
    assert restored._state_inputs[0]['path'] == str(moved / 'subjects.csv')
    pd.testing.assert_frame_equal(restored.summary, state.summary)


def test_nested_batch_rebases_children_before_rebuilding_image_lookup(tmp_path):
    from PyFLASH.batch import Batch
    from PyFLASH.conditions import ConditionBuilder
    original = tmp_path / 'batch-project'
    original.mkdir()
    child = example(original / 'experiment')
    conditions = ConditionBuilder('Group').add('A').add('B').compare_all_pairs().build()
    batch = Batch('nested', [child], conditions, str(original))
    batch.data = {}
    batch.summary = child.summary.copy()
    save_state(batch, original / 'state.pkl', verbose=False)
    moved = tmp_path / 'moved-batch'
    shutil.copytree(original, moved)
    restored = load_state(moved / 'state.pkl', verbose=False)
    assert restored.filePath == str(moved)
    assert restored.experiment_list[0].filePath == str(moved / 'experiment')
    assert restored.experiment_list[0].images.ImagePath.tolist() == [str(moved / 'experiment' / 'image.png')]
    pd.testing.assert_frame_equal(restored.summary, batch.summary)
