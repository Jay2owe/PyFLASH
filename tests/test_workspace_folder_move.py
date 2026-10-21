"""Recovery identity and all internal result/draft paths follow a moved project."""
import json
from pathlib import Path
from PyFLASH.ui import workspace


def test_actual_project_move_reopens_its_existing_recovery_and_result_paths(tmp_path,monkeypatch):
    original, moved = tmp_path/'original',tmp_path/'moved'
    original.mkdir()
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'local-settings'))
    monkeypatch.chdir(original)
    source, figure = original/'analysis.csv',original/'outputs/figure.svg'
    source.write_bytes(workspace.DEMO_PATH.read_bytes())
    figure.parent.mkdir()
    figure.write_bytes(b'recorded scientific output')
    external = tmp_path/'outside.csv'
    state = {'ui_source':{'kind':'csv','path':str(source)},
        'ui_function_drafts':{'action:mean_bars':{'schema_version':1,'values':{'path':str(source)},
            'style':{'presentation':{'ylim':[-2,12],'legend':'hide'}}}},
        'ui_fn_example_result':{'root':str(figure.parent),'paths':[str(figure)],
            'tables':[{'path':str(external)}]},
        'ui_explore_view_styles':{'relationship_view':{'xlim':[0,20]}}}
    before_path = workspace.recovery_path()
    workspace.checkpoint_session(state)
    raw = json.loads(before_path.read_text())
    assert raw['source']['path'] == 'analysis.csv'
    assert raw['preferences']['ui_fn_example_result']['paths'] == ['outputs/figure.svg']
    assert raw['preferences']['ui_function_drafts']['action:mean_bars']['values']['path'] == 'analysis.csv'
    monkeypatch.chdir(tmp_path)
    assert original.resolve().is_relative_to(tmp_path.resolve()) and moved.resolve().is_relative_to(tmp_path.resolve())
    original.rename(moved)
    monkeypatch.chdir(moved)
    assert workspace.recovery_path() == before_path
    restored = workspace.read_recovery(before_path)
    result = restored['preferences']['ui_fn_example_result']
    assert result['paths'] == [str(moved/'outputs/figure.svg')]
    assert Path(result['paths'][0]).read_bytes() == b'recorded scientific output'
    assert result['root'] == str(moved/'outputs')
    assert result['tables'][0]['path'] == str(external)
    assert restored['preferences']['ui_function_drafts']['action:mean_bars']['style'] == state['ui_function_drafts']['action:mean_bars']['style']


def test_previous_workspace_schema_migrates_in_memory_and_future_schema_fails(tmp_path):
    import pytest
    path = tmp_path/'legacy.json'
    legacy = {'schema_version':1,'source':{'kind':'csv','path':'subjects.csv'},'preferences':{'ui_explore_subject':'A01'}}
    path.write_text(json.dumps(legacy))
    before = path.read_bytes()
    result = workspace.read_recovery(path)
    assert result['schema_version'] == workspace.SCHEMA_VERSION
    assert result['preferences'] == legacy['preferences']
    assert path.read_bytes() == before
    path.write_text(json.dumps({'schema_version':workspace.SCHEMA_VERSION+1}))
    with pytest.raises(ValueError,match='unsupported'):
        workspace.read_recovery(path)


def test_redundant_identity_recovers_saved_edits_after_move_and_primary_corruption(tmp_path, monkeypatch):
    original, moved = tmp_path/'original',tmp_path/'moved'
    original.mkdir()
    monkeypatch.chdir(original)
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'local-settings'))
    recovery = workspace.recovery_path()
    workspace.checkpoint_session({'ui_explore_view_styles': {'relationship_view': {'ylim':[-1,12]}}})
    marker = original/'.pyflash-workspace-id.json'
    damaged = b'partial corrupted identity {'
    marker.write_bytes(damaged)
    monkeypatch.chdir(tmp_path)
    assert original.resolve().is_relative_to(tmp_path.resolve())
    assert moved.resolve().is_relative_to(tmp_path.resolve())
    original.rename(moved)
    monkeypatch.chdir(moved)
    assert workspace.recovery_path() == recovery
    assert (moved/'.pyflash-workspace-id.json').read_bytes() == damaged
    saved = workspace.read_recovery(recovery)
    assert saved['preferences']['ui_explore_view_styles']['relationship_view']['ylim'] == [-1,12]


def test_removed_primary_uses_existing_backup_and_unsupported_primary_is_preserved(tmp_path, monkeypatch):
    import pytest
    monkeypatch.chdir(tmp_path)
    recovery = workspace.recovery_path()
    marker = tmp_path/'.pyflash-workspace-id.json'
    marker.unlink()  # Only the tiny identity created by this test.
    assert workspace.recovery_path() == recovery
    future = b'{"schema_version":99,"identity":"0123456789ab"}'
    marker.write_bytes(future)
    with pytest.raises(ValueError,match='Unsupported'):
        workspace.recovery_path()
    assert marker.read_bytes() == future
