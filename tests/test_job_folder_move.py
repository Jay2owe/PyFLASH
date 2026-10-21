"""Move real job inputs/results, then execute the recovered request."""
import json
import os
from pathlib import Path
from types import SimpleNamespace
import pytest
from PyFLASH.ui import jobs, workspace


def test_queued_request_executes_after_actual_project_move(tmp_path, monkeypatch):
    original, moved = tmp_path/'original', tmp_path/'moved'
    original.mkdir()
    monkeypatch.chdir(original)
    source = original/'subjects.csv'
    source.write_bytes(workspace.DEMO_PATH.read_bytes())
    external = tmp_path/'external-table.csv'
    external.write_bytes(b'original external input')
    monkeypatch.setattr(jobs, '_launch', lambda *args: SimpleNamespace(pid=os.getpid(), poll=lambda: None))
    identity = jobs.start_operation('csv', {'kind': 'csv', 'path': str(source),
        'version': workspace.source_version(source)}, {'region': 'SCN'},
        name='Export', dataset_token='same', target_key='result', root=original/'jobs')
    raw = json.loads((original/'jobs'/identity/'request.json').read_text())
    assert raw['schema_version'] == 2 and raw['source']['path'] == 'subjects.csv'
    raw['external_input'] = {'path': str(external)}
    workspace.write_json(original/'jobs'/identity/'request.json', raw)
    monkeypatch.chdir(tmp_path)
    assert original.resolve().is_relative_to(tmp_path.resolve())
    assert moved.resolve().is_relative_to(tmp_path.resolve())
    original.rename(moved)
    monkeypatch.chdir(moved)
    directory = moved/'jobs'/identity
    restored = workspace.read_operation_state(directory/'request.json')
    assert restored['source']['path'] == str(moved/'subjects.csv')
    assert restored['external_input']['path'] == str(external)
    state = jobs.run_request(directory/'request.json')
    assert state['status'] == 'succeeded', state.get('error')
    key, result = jobs.completed_result(state, 'same', root=moved/'jobs')
    assert key == 'result'
    assert Path(result['path']).is_file()
    assert Path(result['path']).is_relative_to(moved)
    assert Path(result['receipt']).is_file()
    raw_result = json.loads((directory/'result.json').read_text())
    assert not Path(raw_result['path']).is_absolute()
    assert raw_result['schema_version'] == 2


@pytest.mark.parametrize('version', [None, 1])
def test_historical_job_files_migrate_without_rewriting_original(tmp_path, version):
    path = tmp_path/'old.json'
    payload = {'id': 'legacy', 'status': 'succeeded', 'paths': ['old.svg']}
    if version is not None:
        payload['schema_version'] = version
    path.write_text(json.dumps(payload))
    before = path.read_bytes()
    restored = workspace.read_operation_state(path)
    assert restored['schema_version'] == 2 and restored['paths'] == ['old.svg']
    assert path.read_bytes() == before


def test_unsupported_job_version_and_escaping_relative_paths_are_rejected(tmp_path):
    path = tmp_path/'bad.json'
    workspace.write_json(path, {'schema_version': 3})
    with pytest.raises(ValueError, match='unsupported'):
        workspace.read_operation_state(path)
    workspace.write_json(path, {'schema_version': 2, 'path': '../outside.csv', 'relative_paths': [['path']]})
    with pytest.raises(ValueError, match='leaves the project'):
        workspace.read_operation_state(path)
