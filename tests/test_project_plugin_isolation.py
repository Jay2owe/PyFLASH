"""Unrelated installed extensions cannot alter project test discovery."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _child_command(workspace, test):
    return [sys.executable, '-m', 'pytest', '-c', str(ROOT / 'pyproject.toml'),
            '--rootdir=' + str(workspace), '--confcutdir=' + str(workspace),
            str(test), '-q', '-o', 'cache_dir=' + str(workspace / 'cache')]


@pytest.mark.parametrize('selection', ['automatic', 'explicit-good', 'explicit-error'])
def test_actual_pytest_uses_project_owned_extensions_only(tmp_path, selection):
    advertised = tmp_path / 'unrelated_probe-1.0.dist-info'
    advertised.mkdir()
    (advertised / 'METADATA').write_text('Metadata-Version: 2.1\nName: unrelated-probe\nVersion: 1.0\n')
    (advertised / 'entry_points.txt').write_text('[pytest11]\nunrelated_probe = foreign_probe\n')
    marker = tmp_path / 'extension-imported.txt'
    (tmp_path / 'foreign_probe.py').write_text(
        'from pathlib import Path\n'
        f'Path({str(marker)!r}).write_text("imported")\n'
        'raise RuntimeError("unrelated extension must not load automatically")\n')
    (tmp_path / 'owned_probe.py').write_text(
        'from pathlib import Path\n'
        f'Path({str(marker)!r}).write_text("explicit project extension")\n')
    test = tmp_path / 'test_independent_case.py'
    test.write_text('def test_complete_case():\n    assert 2 + 2 == 4\n')
    command = _child_command(tmp_path, test)
    if selection != 'automatic':
        command += ['-p', 'owned_probe' if selection == 'explicit-good' else 'foreign_probe']
    environment = dict(os.environ)
    environment.pop('PYTEST_DISABLE_PLUGIN_AUTOLOAD', None)
    environment.pop('PYTEST_ADDOPTS', None)
    environment['PYTHONPATH'] = str(tmp_path)
    result = subprocess.run(command, cwd=tmp_path, env=environment,
        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)
    output = result.stdout + result.stderr
    if selection == 'explicit-error':
        assert result.returncode != 0 and 'unrelated extension must not load automatically' in output
        assert marker.read_text() == 'imported'
    else:
        assert result.returncode == 0 and '1 passed' in output, output
        if selection == 'automatic':
            assert not marker.exists()
        else:
            assert marker.read_text() == 'explicit project extension'


def test_actual_child_discovery_does_not_enter_unrelated_parent_workspace(tmp_path):
    (tmp_path / 'conftest.py').write_text('raise RuntimeError("unrelated parent configuration was loaded")\n')
    (tmp_path / 'test_unrelated.py').write_text('def test_unrelated():\n    assert False\n')
    workspace = tmp_path / 'owned'
    workspace.mkdir()
    test = workspace / 'test_owned.py'
    test.write_text('def test_owned():\n    assert True\n')
    environment = dict(os.environ)
    environment.pop('PYTEST_DISABLE_PLUGIN_AUTOLOAD', None)
    environment.pop('PYTEST_ADDOPTS', None)
    result = subprocess.run(_child_command(workspace, test), cwd=workspace, env=environment,
        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)
    assert result.returncode == 0 and '1 passed' in result.stdout, result.stdout + result.stderr
