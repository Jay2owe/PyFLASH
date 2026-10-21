"""Known persistence/resource gaps; draft outside frozen source snapshot."""
from pathlib import Path
import json
import pytest
from PyFLASH import queue,actions
from PyFLASH.ui import workspace

def run(path,**kwargs):
    return queue.run_action_grid(None,'PyFLASH.stats.bonferroni_correction',{},
        {'p_value':[.01],'n_tests':[2]},path,**kwargs)

@pytest.mark.parametrize('change',[
    {'schema_version':999},{'schema_version':True},{'status':'unexpected'},
    {'outputs':[]},{'key':'wrong-content-identity'},
])
def test_grid_refuses_damaged_cache_before_any_progress_write(tmp_path,monkeypatch,change):
    path=tmp_path/'progress.json'
    first=run(path)
    accepted=Path(first['results'][0]['receipt'])
    state=json.loads(accepted.read_text())
    main=accepted.parent.parent/'cell.json'
    state.update(change)
    main.write_text(json.dumps(state))
    before=path.read_bytes()
    cache_before=main.read_bytes()
    monkeypatch.setattr(actions,'call_action',lambda *args:pytest.fail('Damaged cache triggered execution'))
    with pytest.raises(ValueError,match='(?i)(schema|cache|identity|record|status|outputs)'):
        run(path)
    assert path.read_bytes()==before
    assert main.read_bytes()==cache_before

def test_grid_hashes_each_distinct_declared_file_once(tmp_path,monkeypatch):
    source=tmp_path/'table.csv'
    source.write_text('x\n1\n')
    calls=[]
    original=workspace.content_hash
    def record(path):
        if Path(path).resolve()==source.resolve():calls.append(Path(path))
        return original(path)
    monkeypatch.setattr(workspace,'content_hash',record)
    monkeypatch.setattr(actions,'call_action',lambda *args: {'value':1})
    queue.run_action_grid(None,'model_result_matrix',{'path':str(source),'save':False},
        {'vmin':[.1,.2,.3,.4]},tmp_path/'progress.json')
    assert len(calls)==1

def test_insufficient_resources_refuse_before_declared_input_content_read(tmp_path,monkeypatch):
    source=tmp_path/'table.csv'
    source.write_text('x\n1\n')
    monkeypatch.setattr(workspace,'content_hash',lambda *args:pytest.fail('Read file before resource check'))
    with pytest.raises(ValueError,match='available:'):
        queue.run_action_grid(None,'model_result_matrix',{'path':str(source),'save':False},
            {'vmin':[.1,.2]},tmp_path/'progress.json',memory_budget_bytes=1)
    assert not (tmp_path/'progress.json').exists()
    assert not (tmp_path/'cell-cache').exists()


def test_grid_reuses_declared_inputs_after_project_folder_moves(tmp_path, monkeypatch):
    folder = tmp_path/'project-before'
    folder.mkdir()
    source = folder/'table.csv'
    source.write_bytes(b'recorded input')
    calls = []
    def call(action, data, parameters):
        calls.append(parameters['path'])
        return Path(parameters['path']).read_bytes()
    monkeypatch.setattr(actions, 'call_action', call)
    monkeypatch.chdir(folder)
    def execute(root):
        return queue.run_action_grid(None, 'model_result_matrix',
            {'path':str(root/'table.csv'), 'save':False}, {'vmin':[.1,.2]}, root/'progress.json')
    first = execute(folder)
    keys = [row['key'] for row in first['results']]
    for row in first['results']:
        record = json.loads(Path(row['receipt']).read_text())
        assert not Path(record['parameters']['path']).is_absolute()
        assert not Path(record['input_files'][0]['path']).is_absolute()
    monkeypatch.chdir(tmp_path)
    moved = tmp_path/'project-after'
    assert folder.resolve().is_relative_to(tmp_path.resolve()) and moved.resolve().is_relative_to(tmp_path.resolve())
    folder.rename(moved)
    monkeypatch.chdir(moved)
    second = execute(moved)
    assert [row['key'] for row in second['results']] == keys
    assert all(row['reused'] and row['result'] == b'recorded input' for row in second['results'])
    assert len(calls) == 2


def test_grid_reuses_explicit_legacy_record_without_overwriting_it(tmp_path, monkeypatch):
    progress = tmp_path/'progress.json'
    first = run(progress)
    accepted = Path(first['results'][0]['receipt'])
    main = accepted.parent.parent/'cell.json'
    record = json.loads(main.read_text())
    record['schema_version'] = 1
    record.pop('relative_paths')
    main.write_text(json.dumps(record))
    before = main.read_bytes()
    monkeypatch.setattr(actions, 'call_action', lambda *args:pytest.fail('Legacy completed result was rerun'))
    second = run(progress)
    assert second['results'][0]['reused']
    assert main.read_bytes() == before
    assert json.loads(progress.read_text())['schema_version'] == 2


def test_declared_read_only_support_action_survives_a_fresh_process_project_move(tmp_path, monkeypatch):
    import os
    import subprocess
    from reproducibility.run import python_command
    folder = tmp_path/'project-before'
    folder.mkdir()
    source = folder/'project.json'
    source.write_text(json.dumps({'schema_version':1, 'name':'Portable saved setup'}))
    monkeypatch.chdir(folder)
    first = queue.run_action_grid(None, 'PyFLASH.ui.project_io.load_project', {},
        {'path':[str(source)]}, folder/'progress.json')
    assert first['results'][0]['result'].name == 'Portable saved setup'
    expected = first['results'][0]['key']
    monkeypatch.chdir(tmp_path)
    moved = tmp_path/'project-after'
    assert folder.resolve().is_relative_to(tmp_path.resolve()) and moved.resolve().is_relative_to(tmp_path.resolve())
    folder.rename(moved)
    command = (
        "import json;from pathlib import Path;from PyFLASH.queue import run_action_grid;"
        "root=Path.cwd();result=run_action_grid(None,'PyFLASH.ui.project_io.load_project',{},"
        "{'path':[str(root/'project.json')]},root/'progress.json');"
        "row=result['results'][0];print(json.dumps({'reused':row['reused'],"
        "'key':row['key'],'name':row['result'].name}))")
    result = subprocess.run(python_command()+['-c',command],cwd=moved,
        capture_output=True,text=True,timeout=90,env=dict(os.environ,MPLBACKEND='Agg'))
    assert result.returncode == 0, result.stdout+result.stderr
    assert json.loads(result.stdout) == {'reused':True,'key':expected,'name':'Portable saved setup'}
