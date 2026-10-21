"""Feature repair uses declared requirements and the same public action."""
from types import SimpleNamespace
import json

import pytest

from PyFLASH import dependencies
from PyFLASH.actions import call_action
from PyFLASH.control import describe, doctor
from PyFLASH.ui import jobs


def test_doctor_covers_every_declared_requirement_and_version_bound():
    records = doctor()
    assert {entry['package'] for entry in records} == set(dependencies.registry())
    assert next(entry for entry in records if entry['package'] == 'reprofig')['specifier'] == '<0.6,>=0.5.1'
    assert describe('PyFLASH.dependencies.repair')['access'] == 'mutating'
    assert describe('PyFLASH.dependencies.check')['access'] == 'read-only'


def test_public_spreadsheet_writer_is_declared_as_a_core_dependency():
    records = dependencies.check('core')
    writer = next(entry for entry in records if entry['package'].lower() == 'xlsxwriter')
    assert writer['specifier'] == '>=3.0' and not writer['optional']


def test_incompatible_installed_version_is_not_healthy(monkeypatch):
    original = dependencies.version
    monkeypatch.setattr(dependencies, 'version', lambda package: '0.1' if package == 'reprofig' else original(package))
    entry = next(entry for entry in dependencies.check() if entry['package'] == 'reprofig')
    assert entry['version'] == '0.1' and not entry['compatible']
    assert '<0.6,>=0.5.1' in entry['repair']


def test_unknown_repair_cannot_invoke_pip(monkeypatch):
    monkeypatch.setattr(dependencies.subprocess, 'run', lambda *a, **k: pytest.fail('Unexpected install'))
    with pytest.raises(ValueError, match='Unknown dependency'):
        call_action('PyFLASH.dependencies.repair', parameters={'package': 'undeclared-package'})


def test_repair_uses_exact_requirement_and_verifies_success(monkeypatch):
    observed = []
    def run(command, **kwargs):
        observed.append(command)
        return SimpleNamespace(returncode=0, stdout='installed', stderr='')
    monkeypatch.setattr(dependencies.subprocess, 'run', run)
    result = call_action('PyFLASH.dependencies.repair', parameters={'package': 'reprofig'})
    assert result['compatible']
    assert observed[0][-4:] == ['-m', 'pip', 'install', 'reprofig<0.6,>=0.5.1']


def test_repair_retains_requested_backend_extras(monkeypatch):
    observed=[]
    original_version=dependencies.version
    original_requires=dependencies.requires
    monkeypatch.setattr(dependencies,'version',lambda name:
        '0.5.0' if name=='ai-ify' else original_version(name))
    monkeypatch.setattr(dependencies,'requires',lambda name:
        [] if name=='ai-ify' else original_requires(name))
    monkeypatch.setattr(dependencies.subprocess,'run',lambda command,**kwargs:
        observed.append(command) or SimpleNamespace(returncode=0,stdout='installed',stderr=''))
    result=dependencies.repair('ai-ify')
    assert result['compatible']
    assert observed[0][-1]=='ai-ify[web]<0.6,>=0.5.0'


def test_missing_web_dependency_keeps_backend_repair_available(monkeypatch):
    original=dependencies.version
    original_requires=dependencies.requires
    monkeypatch.setattr(dependencies,'requires',lambda name:
        ['fastapi>=0.115; extra == "web"','pytest>=99; extra == "test"']
        if name=='ai-ify' else original_requires(name))
    def version(package):
        if package=='fastapi':
            raise dependencies.PackageNotFoundError(package)
        if package=='ai-ify':
            return '0.5.0'
        return original(package)
    monkeypatch.setattr(dependencies,'version',version)
    record=next(item for item in dependencies.check('ai') if item['package']=='ai-ify')
    assert record['version']=='0.5.0' and not record['compatible']
    assert record['repair']=='python -m pip install "ai-ify[web]<0.6,>=0.5.0"'
    assert next(item for item in record['extra_dependencies'] if item['package']=='fastapi')['version'] is None
    assert not any(item['package']=='pytest' for item in record['extra_dependencies'])


def test_failed_install_reports_failure(monkeypatch):
    monkeypatch.setattr(dependencies.subprocess, 'run', lambda *a, **k:
        SimpleNamespace(returncode=1, stdout='', stderr='network unavailable'))
    with pytest.raises(RuntimeError, match='network unavailable'):
        dependencies.repair('reprofig')


def test_successful_repair_retries_previously_missing_optional_backend(monkeypatch):
    from PyFLASH import _optional
    _optional._CACHE['missing-backend'] = None
    monkeypatch.setattr(dependencies.subprocess, 'run', lambda *a, **k:
        SimpleNamespace(returncode=0, stdout='installed', stderr=''))
    dependencies.repair('reprofig')
    assert 'missing-backend' not in _optional._CACHE


def test_unknown_dependency_group_cannot_report_a_clean_environment():
    with pytest.raises(ValueError, match='Unknown dependency group'):
        dependencies.check('misspelled-extra')


def test_actual_workspace_uses_declared_dependency_registry_without_stale_groups(monkeypatch, tmp_path):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    from PyFLASH.ui import workspace
    monkeypatch.setattr(workspace, 'recovery_path', lambda: tmp_path / 'workspace.json')
    app = AppTest.from_file(str(Path('PyFLASH/ui/app.py').resolve())).run(timeout=30)
    assert not app.exception


def test_background_repair_needs_no_dataset_file_and_retains_failure(tmp_path, monkeypatch):
    class Child:
        pid = 12345
        def poll(self): return None
    monkeypatch.setattr(jobs, '_launch', lambda *a: Child())
    identifier = jobs.start_dependency_repair('pointpats', dataset_token='current', root=tmp_path)
    request_path = tmp_path / identifier / 'request.json'
    request = json.loads(request_path.read_text())
    assert request['action'] == 'PyFLASH.dependencies.repair' and 'source' not in request
    monkeypatch.setattr(dependencies, 'repair', lambda package: (_ for _ in ()).throw(RuntimeError('install failed')))
    state = jobs.run_request(request_path)
    assert state['status'] == 'failed' and state['error'] == 'install failed'


def test_source_free_action_has_a_result_receipt_and_standalone_script(tmp_path, monkeypatch):
    class Child:
        pid = 12345
        def poll(self): return None
    monkeypatch.setattr(jobs, '_launch', lambda *a: Child())
    identifier = jobs.start_value_action('PyFLASH.stats.bonferroni_correction',
        {'p_value': .03, 'n_tests': 2}, name='Correction', dataset_token='current',
        target_key='ui_result', root=tmp_path)
    directory = tmp_path / identifier
    state = jobs.run_request(directory / 'request.json')
    assert state['status'] == 'succeeded'
    result = json.loads((directory / 'result.json').read_text())
    assert result['value'] == .06
    assert 'CODE_IDENTITY' in result['script'] and 'DEPENDENCIES' in result['script']
    record = json.loads((directory / 'run.json').read_text())
    assert record['source'] is None and record['parameters']['n_tests'] == 2
    assert record['code_sha256'] and record['dependencies']['numpy']
