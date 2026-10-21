"""Grid reuse, interruption, output ownership and resource refusal."""
import json
from pathlib import Path
import pytest
from PyFLASH import queue

ACTION = 'PyFLASH.stats.bonferroni_correction'


def run(tmp_path, choices=None, **kwargs):
    return queue.run_action_grid(None, ACTION, {}, choices or {'p_value':[.01,.02], 'n_tests':[2,3]},
        tmp_path / 'progress.json', **kwargs)


def test_grid_runs_cartesian_product_then_reuses_every_cell(tmp_path, monkeypatch):
    first = run(tmp_path)
    assert not first['pending'] and not first['failures']
    assert sorted(row['result'] for row in first['results']) == [.02,.03,.04,.06]
    from PyFLASH import actions
    monkeypatch.setattr(actions, 'call_action', lambda *args:pytest.fail('Finished cell was recomputed.'))
    second = run(tmp_path)
    assert all(row['reused'] for row in second['results'])


def test_changing_one_value_reuses_only_the_unchanged_cells(tmp_path):
    run(tmp_path)
    changed = run(tmp_path, {'p_value':[.01,.04], 'n_tests':[2,3]})
    assert [row['reused'] for row in changed['results']] == [True,False,True,False]
    assert sorted(row['result'] for row in changed['results']) == [.02,.03,.08,.12]


def test_cancel_preserves_completed_cells_and_resume_reuses_them(tmp_path):
    cancel = tmp_path / 'cancel'
    def complete(item, result):
        assert item['index'] == 0 and result['result'] == .02
        cancel.touch()
    first = run(tmp_path, cancel_path=cancel, on_cell=complete)
    assert first['cancelled'] and first['pending'] == [1,2,3]
    cancel.unlink()  # This test owns the small cancellation marker.
    resumed = run(tmp_path)
    assert [row['reused'] for row in resumed['results']] == [True,False,False,False]


def test_failed_cells_keep_attempts_while_others_finish(tmp_path, monkeypatch):
    from PyFLASH import actions
    original = actions.call_action
    def fail_one(action, data, parameters):
        if parameters == {'n_tests':2,'p_value':.02}:
            raise ValueError('controlled failure')
        return original(action, data, parameters)
    monkeypatch.setattr(actions, 'call_action', fail_one)
    first = run(tmp_path)
    assert len(first['failures']) == 1 and len(first['results']) == 3
    monkeypatch.setattr(actions, 'call_action', original)
    resumed = run(tmp_path)
    assert not resumed['failures'] and sum(row['reused'] for row in resumed['results']) == 3
    failed = next(row for row in resumed['results'] if not row['reused'])
    assert [row['status'] for row in json.loads(Path(failed['receipt']).read_text())['attempts']] == ['failed','done']


@pytest.mark.parametrize('kwargs', [{'memory_budget_bytes':1}, {'disk_budget_bytes':1}])
def test_resources_refuse_before_creating_outputs(tmp_path, kwargs):
    with pytest.raises(ValueError, match='available:'):
        run(tmp_path, **kwargs)
    assert not (tmp_path / 'progress.json').exists()
    assert not (tmp_path / 'cell-cache').exists()


def test_oversized_cartesian_grid_refuses_before_allocation(tmp_path):
    with pytest.raises(ValueError, match='10000 cells; the limit is 64'):
        run(tmp_path, {'p_value':[.01]*100, 'n_tests':list(range(100))})
    assert not (tmp_path / 'progress.json').exists()


def test_changed_cached_result_is_never_reused(tmp_path):
    first = run(tmp_path)
    receipt = Path(first['results'][0]['receipt'])
    record = json.loads(receipt.read_text())
    (receipt.parent / record.get('root_relative', '.') / record['result']).write_bytes(b'changed output')
    with pytest.raises(ValueError, match='lost or changed an output'):
        run(tmp_path)


def test_unknown_option_refuses_before_any_cell_runs(tmp_path):
    with pytest.raises(TypeError, match='piont'):
        queue.run_action_grid(None, ACTION, {'p_value':.01, 'n_tests':2},
                              {'piont':[True,False]}, tmp_path / 'progress.json')
    assert not (tmp_path / 'progress.json').exists()


def test_optional_dataset_plot_grid_owns_every_cell_and_reuses_complete_curves(tmp_path):
    result = queue.run_action_grid(None, 'power_curve',
        {'n_range': [2,3], 'save': False, 'return_data': True},
        {'effect_sizes': [[.2],[.8]]}, tmp_path/'optional.json')
    assert not result['failures'] and len(result['results']) == 2
    tables = [row['result'][1].copy() for row in result['results']]
    assert all(len(table) == 2 for table in tables)
    replay = queue.run_action_grid(None, 'power_curve',
        {'n_range': [2,3], 'save': False, 'return_data': True},
        {'effect_sizes': [[.2],[.8]]}, tmp_path/'optional.json')
    import pandas as pd
    for first, second in zip(tables,replay['results'],strict=True):
        assert second['reused']
        pd.testing.assert_frame_equal(first,second['result'][1],check_exact=True)


def test_file_input_changes_create_new_cells_without_overwriting_prior_evidence(tmp_path, monkeypatch):
    from PyFLASH import actions
    source = tmp_path/'model-table.csv'
    source.write_bytes(b'first input contents')
    calls = []
    def execute(action, data, parameters):
        value = Path(parameters['path']).read_bytes()
        calls.append(value)
        return value
    monkeypatch.setattr(actions, 'call_action', execute)
    def run_table():
        return queue.run_action_grid(None, 'model_result_matrix',
            {'path': str(source), 'save': False}, {'vmin': [0.,.1]}, tmp_path/'file-grid.json')
    before = run_table()
    assert len(calls) == 2
    assert all(row['input_files'][0]['path'] == str(source) for row in before['results'])
    assert all(row['reused'] for row in run_table()['results'])
    source.write_bytes(b'changed input contents')
    after = run_table()
    assert len(calls) == 4 and not any(row['reused'] for row in after['results'])
    assert {row['receipt'] for row in before['results']}.isdisjoint(row['receipt'] for row in after['results'])
    assert all(Path(row['receipt']).is_file() for row in before['results'])
    assert all(row['result'] == b'changed input contents' for row in after['results'])


def test_grid_refuses_missing_file_inputs_before_creating_progress_or_cells(tmp_path):
    with pytest.raises(FileNotFoundError, match='Missing input'):
        queue.run_action_grid(None, 'model_result_matrix', {'path': str(tmp_path/'missing.csv')},
                              {'vmin': [0.,.1]}, tmp_path/'missing.json')
    assert not (tmp_path/'missing.json').exists()
    assert not (tmp_path/'cell-cache').exists()


def test_appearance_and_optional_backend_changes_do_not_reuse_old_cells(tmp_path, monkeypatch):
    from PyFLASH.aesthetics import pyflash_style_context
    from PyFLASH import dependencies
    original = dependencies.check
    with pyflash_style_context(point_size=7):
        first = run(tmp_path)
        assert not any(row['reused'] for row in first['results'])
        assert all(row['reused'] for row in run(tmp_path)['results'])
    with pyflash_style_context(point_size=11):
        assert not any(row['reused'] for row in run(tmp_path)['results'])
        def changed(group=None):
            return [dict(entry, version='controlled-backend-version')
                    if entry['package'] == 'pointpats' else entry
                    for entry in original(group)]
        monkeypatch.setattr(dependencies, 'check', changed)
        assert not any(row['reused'] for row in run(tmp_path)['results'])
