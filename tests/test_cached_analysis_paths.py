"""A scientific cached result must move with its project without live edits."""
from pathlib import Path
import pandas as pd
from PyFLASH import queue, actions, from_dataframe


def test_cached_analysis_preserves_measurements_and_rebases_internal_paths(tmp_path, monkeypatch):
    root = tmp_path/'before'
    root.mkdir()
    source = root/'subjects.csv'
    source.write_text('AnimalName,Condition,Signal\nA01,A,1.25\nB01,B,3.5\n')
    frame = pd.read_csv(source)
    analysis = from_dataframe(frame, group_col='Condition', subject_col='AnimalName',
        file_path=str(root), source_paths=[str(source)])
    analysis.images = pd.DataFrame({'AnimalName':['A01'], 'ImagePath':[str(root/'a.png')]})
    external = tmp_path/'external.csv'
    external.write_text('outside project')
    analysis.source_paths = [str(source),str(external)]
    original = analysis.images.copy(deep=True)
    monkeypatch.setattr(actions, 'call_action', lambda *args:analysis)
    monkeypatch.chdir(root)
    def run(folder):
        return queue.run_action_grid(None, 'PyFLASH.stats.bonferroni_correction', {},
            {'p_value':[.01], 'n_tests':[2]},folder/'progress.json')['results'][0]
    first = run(root)
    assert analysis.filePath == str(root)
    assert analysis.source_paths == [str(source),str(external)]
    pd.testing.assert_frame_equal(analysis.images, original)
    monkeypatch.chdir(tmp_path)
    moved = tmp_path/'after'
    assert root.resolve().is_relative_to(tmp_path.resolve()) and moved.resolve().is_relative_to(tmp_path.resolve())
    root.rename(moved)
    monkeypatch.chdir(moved)
    monkeypatch.setattr(actions, 'call_action', lambda *args: (_ for _ in ()).throw(AssertionError('Cached call reran')))
    second = run(moved)
    assert second['reused'] and second['key'] == first['key']
    result = second['result']
    assert result.filePath == str(moved)
    assert result.source_paths == [str(moved/'subjects.csv'),str(external)]
    assert result.images.ImagePath.tolist() == [str(moved/'a.png')]
    assert result.fig_path == str(moved/'Results'/'Python Figures')
    pd.testing.assert_frame_equal(result.summary, analysis.summary)
