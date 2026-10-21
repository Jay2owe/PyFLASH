"""Browser backend operations remain usable through the public dispatcher/CLI."""
import json
from pathlib import Path

import pandas as pd
import pytest

from PyFLASH import actions, control
from PyFLASH.ui import workspace, services


def test_every_support_action_describes_its_actual_owner_and_access():
    for key, (title, binding, access) in actions.SUPPORT_ACTIONS.items():
        record = control.describe(key)
        assert record['owner'] == key
        assert record['documentation'] and record['access'] == access


def test_cli_workspace_settings_can_save_and_reopen(tmp_path, capsys):
    path = tmp_path / 'workspace.json'
    state = {'ui_explore_subject': 'A01', 'ui_fold_process.advanced': True}
    parameters = {'state': state, 'path': str(path)}
    code = control.main(['run', 'PyFLASH.ui.workspace.checkpoint_session', '--params', json.dumps(parameters),
                         '--output', str(tmp_path / 'receipt')])
    assert code == 0
    capsys.readouterr()
    result = actions.call_action('PyFLASH.ui.workspace.read_recovery', parameters={'path': str(path)})
    assert result['preferences'] == state
    assert control.describe('PyFLASH.ui.workspace.read_recovery')['access'] == 'read-only'


def test_subject_selection_does_not_change_the_analysis():
    batch = workspace.load_table(workspace.DEMO_PATH, demo=True)
    before = batch.summary.copy(deep=True)
    state = {'batch': batch}
    actions.call_action('PyFLASH.ui.workspace.set_preferences', parameters={
        'state': state, 'updates': {'ui_explore_subject': 'A01', 'ui_explore_point_size': 30}})
    assert state['ui_explore_subject'] == 'A01'
    pd.testing.assert_frame_equal(batch.summary, before)
    with pytest.raises(ValueError, match='not a display setting'):
        actions.call_action('PyFLASH.ui.workspace.set_preferences', parameters={'state': state, 'updates': {'batch': {}}})
    assert state['batch'] is batch


def test_project_setup_and_image_edits_use_the_same_backend(tmp_path):
    project = {'name': 'Shared setup', 'batch_path': str(tmp_path / 'inputs')}
    path = tmp_path / 'project.json'
    actions.call_action('PyFLASH.ui.project_io.save_project', parameters={'project': project, 'path': str(path)})
    loaded = actions.call_action('PyFLASH.ui.project_io.load_project', parameters={'path': str(path)})
    assert loaded.name == project['name'] and loaded.batch_path == project['batch_path']
    batch = workspace.load_table(workspace.DEMO_PATH, demo=True)
    table = [{'AnimalName': 'A01', 'ImagePath': str(tmp_path / 'one.tif')}]
    actions.call_action('PyFLASH.ui.services.set_representative_selections', batch, {'df': table})
    pd.testing.assert_frame_equal(services.get_representative_selections(batch), pd.DataFrame(table))


def test_support_parameter_typo_fails_before_writing(tmp_path, capsys):
    destination = tmp_path / 'receipt'
    assert control.main(['run', 'PyFLASH.ui.workspace.read_recovery', '--params', '{"paht":"missing"}',
                         '--output', str(destination)]) == 1
    assert not destination.exists()
    assert 'paht' in capsys.readouterr().out
