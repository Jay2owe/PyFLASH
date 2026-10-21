import json
from pathlib import Path

import pytest

from scripts.check_ui_comparisons import wait_for_terminal_job


def test_comparison_job_state_retries_transient_windows_lock(tmp_path, monkeypatch):
    state_path = tmp_path / 'state.json'
    original_read_text = Path.read_text
    attempts = 0

    def locked_once(path, *args, **kwargs):
        nonlocal attempts
        if path == state_path:
            attempts += 1
            if attempts == 1:
                raise PermissionError('atomic replacement in progress')
        return original_read_text(path, *args, **kwargs)

    state_path.write_text(json.dumps({'status': 'succeeded'}), encoding='utf-8')
    monkeypatch.setattr(Path, 'read_text', locked_once)

    state = wait_for_terminal_job(tmp_path, {'queued', 'running'}, timeout=0.2, poll_interval=0.001)

    assert attempts == 2
    assert state == {'status': 'succeeded'}


def test_comparison_job_state_timeout_preserves_last_read_error(tmp_path, monkeypatch):
    state_path = tmp_path / 'state.json'

    def always_locked(path, *args, **kwargs):
        if path == state_path:
            raise PermissionError('persistent lock')
        return Path.read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'read_text', always_locked)

    with pytest.raises(TimeoutError, match='PermissionError: persistent lock'):
        wait_for_terminal_job(tmp_path, {'queued', 'running'}, timeout=0.01, poll_interval=0.001)
