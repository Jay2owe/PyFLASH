"""Rare-setting disclosures have explicit keys and persist through recovery."""
from types import SimpleNamespace
import pytest
from PyFLASH.ui import controls, workspace


def test_fold_registry_has_unique_keys_labels_and_icons():
    assert len(controls.FOLDS) == len(set(controls.FOLDS))
    assert all(entry['label'] and entry['icon'] for entry in controls.FOLDS.values())


def test_fold_uses_native_tracked_state_and_shared_recovery(tmp_path, monkeypatch):
    import streamlit as st
    recorded = []
    monkeypatch.setattr(st, 'expander', lambda label, **kwargs: recorded.append((label, kwargs)))
    controls.fold('process.advanced')
    label, kwargs = recorded[0]
    assert label == 'Advanced'
    assert kwargs['key'] == 'ui_fold_process.advanced'
    assert callable(kwargs['on_change'])
    assert kwargs['icon'] == ':material/settings:'
    state = {'ui_fold_process.advanced': True}
    path = tmp_path / 'workspace.json'
    workspace.checkpoint_session(state, path)
    assert workspace.read_recovery(path)['preferences']['ui_fold_process.advanced'] is True


def test_unknown_fold_is_rejected():
    with pytest.raises(KeyError):
        controls.fold('unknown-fold')
