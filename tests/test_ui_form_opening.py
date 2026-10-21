"""Bound repeated form work without weakening source freshness or saved inputs."""
from concurrent.futures import ThreadPoolExecutor
import os

import pytest

from PyFLASH.ui import catalogue, function_contracts as fc


def test_render_shares_one_source_read_and_releases_snapshot_on_error(monkeypatch):
    original = catalogue.functions
    calls = []
    def read():
        calls.append(1)
        return original()
    monkeypatch.setattr(catalogue, 'functions', read)
    with pytest.raises(RuntimeError):
        with fc.catalogue_snapshot():
            first = fc.find('mean_bars')
            with fc.catalogue_snapshot():
                assert fc.find('mean_bars') is first
                fc.catalogue_contracts()
                fc.coverage_document('functions')
            assert len(calls) == 1
            # A different script thread must not inherit this request's facts.
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(fc.find, 'mean_bars').result()
            assert len(calls) == 2
            raise RuntimeError('aborted rerun')
    fc.find('mean_bars')
    assert len(calls) == 3


def test_next_render_detects_same_size_same_timestamp_source_edit(tmp_path, monkeypatch):
    source = tmp_path / 'toy.py'
    source.write_text('def plot_images(value=3):\n    pass\n', encoding='utf-8')
    monkeypatch.setattr(catalogue, 'ROOT', tmp_path)
    monkeypatch.setattr('PyFLASH.spec.PLOT_REGISTRY', {'images': 'PyFLASH.toy.plot_images'})
    before = source.stat()
    with fc.catalogue_snapshot():
        old = fc.find('images')
        source.write_text('def plot_images(value=4):\n    pass\n', encoding='utf-8')
        os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))
        assert fc.find('images') is old
    with fc.catalogue_snapshot():
        new = fc.find('images')
    assert old.entry.signature == 'plot_images(value=3)'
    assert new.entry.signature == 'plot_images(value=4)'


def test_card_callback_accepts_only_declared_selection(monkeypatch):
    from types import SimpleNamespace
    import streamlit as st
    from PyFLASH.ui import function_cards
    owner = fc.find('mean_bars')
    calls = []
    callbacks = []
    def component(**kwargs):
        callbacks.append(kwargs['on_selected_change'])
        return SimpleNamespace(selected=None)
    monkeypatch.setattr(function_cards, '_component', lambda: component)
    state = {'function_cards': SimpleNamespace(selected=None)}
    monkeypatch.setattr(st, 'session_state', state)
    function_cards.render([owner], on_select=lambda *args: calls.append(args))
    for event in ({'key': owner.entry.key, 'operation': 'execute'},
                  {'key': 'unknown', 'operation': 'select'}):
        state['function_cards'].selected = event
        callbacks[0]()
    assert not calls
    state['function_cards'].selected = {'key': owner.entry.key, 'operation': 'select'}
    callbacks[0]()
    assert calls == [(owner.entry, 'select')]


def test_workspace_reuses_duplicate_path_resolution_only_within_one_write(tmp_path, monkeypatch):
    from pathlib import Path
    from PyFLASH.ui import workspace
    monkeypatch.chdir(tmp_path)
    target = tmp_path / 'figure.svg'
    target.write_text('first', encoding='utf-8')
    payload = {'current': {'path': str(target)}, 'history': [{'path': str(target)}]}
    original = Path.resolve
    visits = []
    def resolve(path, *args, **kwargs):
        visits.append(str(path))
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'resolve', resolve)
    converted, locations = workspace._portable_workspace_paths(payload)
    assert converted == {'current': {'path': 'figure.svg'}, 'history': [{'path': 'figure.svg'}]}
    assert locations == [['current', 'path'], ['history', 0, 'path']]
    assert visits.count(str(target)) == 1
    workspace._portable_workspace_paths(payload)
    assert visits.count(str(target)) == 2


def test_form_render_reads_catalogue_once_and_saves_each_selected_draft(monkeypatch):
    import pandas as pd
    from PyFLASH import from_dataframe
    from PyFLASH.ui import function_cards, workspace, jobs, dependency_controls
    from streamlit.testing.v1 import AppTest
    items = catalogue.functions()
    reads, saved = [], []
    def read():
        reads.append(1)
        return items
    monkeypatch.setattr(catalogue, 'functions', read)
    monkeypatch.setattr(function_cards, 'render', lambda *a, **k: None)
    monkeypatch.setattr(jobs, 'latest_job', lambda: None)
    monkeypatch.setattr(dependency_controls, 'check', lambda group: [])
    monkeypatch.setattr(workspace, 'checkpoint_session', lambda state: saved.append(state['ui_function_selection']))
    app = AppTest.from_file('PyFLASH/ui/pages/9_functions.py', default_timeout=30)
    app.session_state['_workspace_initialised'] = True
    app.session_state['ui_function_selection'] = 'action:mean_bars'
    app.session_state['batch'] = from_dataframe(pd.DataFrame({'Condition': ['A','B'], 'Signal': [1.,2.]}), group_col='Condition')
    app.run()
    assert not app.exception and len(reads) == 1
    app.session_state['ui_function_selection'] = 'action:regressions'
    app.run()
    assert not app.exception and len(reads) == 2
    assert saved == ['action:mean_bars', 'action:regressions']
