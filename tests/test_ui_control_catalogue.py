"""Shared native controls retain help and stable durable identities."""
from PyFLASH.ui import controls


class Native:
    def __getattr__(self, kind):
        return lambda *args, **kwargs: (kind, args, kwargs)


def test_every_builder_kind_has_help_home_icon_and_stable_key():
    native = Native()
    for kind in controls.CONTROL_ICONS:
        if kind == 'data_editor':
            continue
        transient = kind in {'button', 'download_button', 'file_uploader', 'form_submit_button'}
        key = ('_control_event_' if transient else 'ui_control_')+kind
        first = controls.widget(native, kind, 'A labelled control', key=key)
        second = controls.widget(native, kind, 'A renamed control', key=key)
        assert first[2]['key'] == second[2]['key']
        metadata = controls.CONTROL_CATALOGUE[first[2]['key']]
        assert all(metadata[name] for name in ('label', 'home', 'help', 'icon', 'kind'))
        assert first[2]['help'] == 'A labelled control.'
        assert first[2]['key'].startswith('_control_event_' if kind in
            {'button', 'download_button', 'file_uploader', 'form_submit_button'} else 'ui_control_')


def test_every_actual_control_declares_its_identity_separately():
    import ast
    from pathlib import Path
    paths = list(Path(controls.__file__).parent.rglob('*.py'))
    count = 0
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'widget':
                assert any(value.arg == 'key' for value in node.keywords), (path.name, node.lineno)
                count += 1
    assert count > 100


def test_original_key_help_and_icon_survive_builder():
    result = controls.widget(Native(), 'button', 'Run', key='explicit',
                             help='Runs the selected analysis.', icon=':material/play_arrow:')
    assert result[2] == {'key':'explicit', 'help':'Runs the selected analysis.', 'icon':':material/play_arrow:'}


def test_draft_control_restore_preserves_live_changes_and_rejects_other_function():
    from PyFLASH.ui import function_contracts as fc, function_workbench as fw
    entry = fc.find('action:mean_bars').entry
    other = fc.find('action:regressions').entry
    key = fw._key(entry, 'advanced_open')
    state = {key:True, fw._key(entry, 'normalize_mode'):'None',
             fw._key(entry, 'result'):{'unserializable':object()}}
    draft = {'controls':fw.draft_controls(state, entry)}
    assert 'result' not in str(draft)
    reopened = {key:False}
    fw.restore_draft_controls(reopened, entry, draft)
    assert reopened[key] is False
    assert reopened[fw._key(entry, 'normalize_mode')] == 'None'
    assert not fw.draft_controls(reopened, other)


def test_source_free_helper_form_runs_without_a_dataset(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from PyFLASH.ui import function_cards, jobs
    monkeypatch.setattr(function_cards, 'render', lambda *a, **k:None)
    monkeypatch.setattr(jobs, 'latest_job', lambda:None)
    submitted = []
    monkeypatch.setattr(jobs, 'start_value_action', lambda *a, **k:submitted.append((a,k)))
    app = AppTest.from_string("from PyFLASH.ui import function_contracts as fc, function_workbench as fw\nfw.render(fc.find('PyFLASH.stats.bonferroni_correction'))", default_timeout=20)
    app.session_state['_ui_dataset_token'] = 'no-dataset'
    app.run()
    assert not app.exception
    app.number_input[0].set_value(.01)
    app.number_input[1].set_value(3).run()
    from PyFLASH.ui import function_contracts as fc, function_workbench as fw
    entry = fc.find('PyFLASH.stats.bonferroni_correction').entry
    app.button(key=fw._key(entry, 'run')).click().run()
    assert not app.exception
    assert submitted[0][0] == ('PyFLASH.stats.bonferroni_correction', {'p_value':.01, 'n_tests':3})
