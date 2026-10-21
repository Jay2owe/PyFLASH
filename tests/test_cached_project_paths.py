"""A cached project must reopen its complete paths in the moved project."""
import json
from pathlib import Path
from PyFLASH import queue


def test_cached_project_restores_all_project_owned_paths(tmp_path, monkeypatch):
    before = tmp_path/'before'
    before.mkdir()
    source = before/'project.json'
    source.write_text(json.dumps({'schema_version':1, 'name':'Recorded setup',
        'batch_path':'outputs', 'pickle_path':'pickles', 'experiments':{'exp':'data'},
        'experiment_paths':['data']}))
    monkeypatch.chdir(before)
    def run(root):
        return queue.run_action_grid(None,'PyFLASH.ui.project_io.load_project',{},
            {'path':[str(root/'project.json')]}, root/'progress.json')['results'][0]
    first = run(before)
    first_values = first['result'].to_dict()
    monkeypatch.chdir(tmp_path)
    after = tmp_path/'after'
    assert before.resolve().is_relative_to(tmp_path.resolve()) and after.resolve().is_relative_to(tmp_path.resolve())
    before.rename(after)
    monkeypatch.chdir(after)
    second = run(after)
    assert second['reused'] and second['key']==first['key']
    expected = {**first_values, 'batch_path':str(after/'outputs'), 'pickle_path':str(after/'pickles'),
                'experiments':{'exp':str(after/'data')}, 'experiment_paths':[str(after/'data')]}
    assert second['result'].to_dict()==expected
