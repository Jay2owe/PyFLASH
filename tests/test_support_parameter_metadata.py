import inspect
import json
import pytest
from PyFLASH import actions, control


@pytest.mark.parametrize('action', list(actions.SUPPORT_ACTIONS))
def test_support_parameters_have_meaning_and_keep_the_live_signature(action):
    description = control.describe(action)
    fn, _, _ = actions.helper_function(action)
    signature = inspect.signature(fn)
    assert [row['name'] for row in description['parameters']] == list(signature.parameters)
    for row in description['parameters']:
        parameter = signature.parameters[row['name']]
        assert row['key'] == parameter.name
        assert row['label'] and row['help'] and row['role']
        assert row['unit'] is None or isinstance(row['unit'], str)
        assert row['choices'] == []
        assert row['kind'] == str(parameter.kind)
        assert row['required'] == (parameter.default is inspect.Parameter.empty)
        assert row['default'] == (None if parameter.default is inspect.Parameter.empty else repr(parameter.default))
        assert {key: row[key] for key in ('key','label','help','role','unit','choices')} == actions.support_parameter_metadata(action)[parameter.name]
    json.dumps(description)


def test_existing_destinations_still_have_output_roles():
    for action in actions.SUPPORT_ACTIONS:
        parameters = {row['name']: row for row in control.describe(action)['parameters']}
        for name in actions.output_parameters(action):
            assert parameters[name]['role'] == 'output'
    assert actions.support_parameter_metadata('PyFLASH.ui.workspace.load_table')['path']['role'] == 'file'
    assert actions.support_parameter_metadata('PyFLASH.ui.services.validate_experiment_folder')['path']['role'] == 'folder'


def test_discovery_never_executes_the_operation(monkeypatch):
    from PyFLASH.ui import jobs
    original = jobs.start_dependency_repair
    def forbidden(*args, **kwargs):
        raise AssertionError('Discovery executed dependency repair')
    forbidden.__signature__ = inspect.signature(original)
    monkeypatch.setattr(jobs, 'start_dependency_repair', forbidden)
    assert control.describe('PyFLASH.ui.jobs.start_dependency_repair')['parameters']


def test_units_are_only_declared_where_the_operation_uses_them():
    log = actions.support_parameter_metadata('PyFLASH.ui.jobs.log_tail')
    grid = actions.support_parameter_metadata('PyFLASH.queue.run_action_grid')
    assert log['max_bytes']['unit'] == 'bytes'
    assert grid['memory_budget_bytes']['unit'] == 'bytes'
    assert grid['disk_budget_bytes']['unit'] == 'bytes'
    assert grid['max_cells']['unit'] == 'cells'
    assert grid['parameters']['unit'] is None


def test_missing_help_fails_discovery_instead_of_silently_omitting_it(monkeypatch):
    monkeypatch.delitem(actions.SUPPORT_PARAMETER_HELP, 'max_bytes')
    with pytest.raises(ValueError, match='Missing support parameter help.*max_bytes'):
        control.describe('PyFLASH.ui.jobs.log_tail')


def test_owner_parameter_help_wins_over_the_backend_vocabulary():
    help_text = actions.support_parameter_metadata('PyFLASH.ui.services.summary_table')['display']['help']
    assert 'human-readable column labels' in help_text


def test_action_specific_path_meanings_do_not_leak_between_operations():
    load = actions.support_parameter_metadata('PyFLASH.ui.workspace.load_table')['path']
    save = actions.support_parameter_metadata('PyFLASH.ui.project_io.save_project')['path']
    recipe = actions.support_parameter_metadata('PyFLASH.queue.run_spec_queue')['path']
    assert 'CSV' in load['help']
    assert 'JSON' in save['help'] and save['role'] == 'output'
    assert 'recipe' in recipe['help'] and recipe['role'] == 'file'


@pytest.mark.parametrize('operation', ['read_job', 'latest_job'])
def test_inspection_access_includes_persisted_dead_worker_recovery(tmp_path, operation):
    from PyFLASH.ui import workspace
    identity = 'a' * 32
    folder = tmp_path / identity
    folder.mkdir()
    workspace.write_operation_state(folder / 'state.json', {
        'schema_version': 1, 'status': 'running', 'worker_pid': None,
        'launcher_pid': None, 'submitted_at': 0, 'id': identity})
    workspace.write_operation_state(tmp_path / 'latest.json', {'id': identity})
    key = 'PyFLASH.ui.jobs.' + operation
    parameters = {'root': str(tmp_path)}
    if operation == 'read_job':
        parameters['job_id'] = identity
    result = actions.call_action(key, parameters=parameters)
    assert result['status'] == 'failed'
    assert workspace.read_operation_state(folder / 'state.json')['status'] == 'failed'
    assert control.describe(key)['access'] == 'mutating'
