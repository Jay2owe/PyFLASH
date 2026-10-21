"""Selections survive restart/moves; older writes cannot replace newer edits."""
import json
import threading
from types import SimpleNamespace

import pandas as pd
import pytest

from PyFLASH import _persistence
from PyFLASH.ui import workspace, services


def test_slow_older_save_cannot_overwrite_completed_newer_save(tmp_path, monkeypatch):
    path = tmp_path / 'workspace.json'
    waiting, release = threading.Event(), threading.Event()
    dump = _persistence.json.dump
    def delayed(payload, stream, **kwargs):
        dump(payload, stream, **kwargs)
        if payload['saved_at_ns'] == 1:
            waiting.set()
            assert release.wait(5)
    monkeypatch.setattr(_persistence.json, 'dump', delayed)
    outcomes = []
    thread = threading.Thread(target=lambda: outcomes.append(_persistence.write_json(
        path, {'saved_at_ns': 1, 'selection': 'older'}, revision_key='saved_at_ns')))
    thread.start()
    assert waiting.wait(5)
    assert _persistence.write_json(path, {'saved_at_ns': 2, 'selection': 'newer'}, revision_key='saved_at_ns')
    release.set()
    thread.join(5)
    assert not thread.is_alive()
    assert outcomes == [False]
    assert json.loads(path.read_text())['selection'] == 'newer'
    assert not list(tmp_path.glob('*.tmp'))


def test_failed_save_preserves_latest_completed_edit(tmp_path, monkeypatch):
    path = tmp_path / 'workspace.json'
    _persistence.write_json(path, {'saved_at_ns': 2, 'selection': 'newer'}, revision_key='saved_at_ns')
    original = path.read_bytes()
    monkeypatch.setattr(_persistence.os, 'replace', lambda *a: (_ for _ in ()).throw(OSError('interrupted')))
    with pytest.raises(OSError, match='interrupted'):
        _persistence.write_json(path, {'saved_at_ns': 3, 'selection': 'failed'}, revision_key='saved_at_ns')
    assert path.read_bytes() == original
    assert not list(tmp_path.glob('*.tmp'))


def test_image_selection_restarts_and_moves_with_its_source(tmp_path, monkeypatch):
    root = tmp_path / 'original'
    root.mkdir()
    source = root / 'analysis.pkl'
    source.write_bytes(b'trusted scientific source')
    recovery = tmp_path / 'recovery.json'
    monkeypatch.setattr(workspace, 'recovery_path', lambda: recovery)
    batch = SimpleNamespace(representative_images=None)
    table = pd.DataFrame({'ImagePath': [str(root / 'images/one.tif'), str(tmp_path / 'outside.tif')],
                          'AnimalName': ['A01', 'B01'], 'Choice': ['first', 'second']}, index=[3, 8])
    state = {'batch': batch, 'ui_source': {'path': str(source), 'kind': 'pickle'}}
    workspace.save_representative_edit(state, table)
    pd.testing.assert_frame_equal(services.get_representative_selections(batch), table)
    saved = workspace.read_recovery(recovery)
    assert saved['preferences']['ui_representative_edits']['relative_paths']['ImagePath'] == [True, False]
    moved = tmp_path / 'moved'
    root.rename(moved)
    restarted = {**saved['preferences'], 'batch': SimpleNamespace(representative_images=None),
                 'ui_source': {'path': str(moved / 'analysis.pkl'), 'kind': 'pickle'}}
    assert workspace.restore_representative_edit(restarted)
    expected = table.copy()
    expected.iloc[0, 0] = str(moved / 'images/one.tif')
    pd.testing.assert_frame_equal(services.get_representative_selections(restarted['batch']), expected)
    (moved / 'analysis.pkl').write_bytes(b'different source')
    with pytest.raises(ValueError, match='different source contents'):
        workspace.restore_representative_edit(restarted)


def test_representative_edits_do_not_leak_to_another_dataset():
    state = {'ui_representative_edits': {'old': True}, 'ui_representative_previous': {'old': True}}
    workspace.activate_dataset(state, object(), {'kind': 'demo', 'path': str(workspace.DEMO_PATH)})
    assert 'ui_representative_edits' not in state and 'ui_representative_previous' not in state
