"""Moved cache results retain types, identities and project-owned path meaning."""
from collections import OrderedDict, namedtuple
from pathlib import Path
import numpy as np
from PyFLASH import queue
from PyFLASH.ui import workspace

PathAndMeasurements = namedtuple('PathAndMeasurements','path measurements')


def test_registered_workspace_result_moves_without_reexecution(tmp_path, monkeypatch):
    before = tmp_path/'before'
    before.mkdir()
    source = before/'subjects.csv'
    source.write_text('AnimalName,Signal\nA01,1.5\n')
    monkeypatch.chdir(before)
    workspace.checkpoint_session({'ui_source':{'kind':'table','path':str(source)},
        'ui_recorded':{'path':str(source),'label':str(source)}},path=before/'workspace.json')
    def run(root):
        return queue.run_action_grid(None,'PyFLASH.ui.workspace.read_recovery',{},
            {'path':[str(root/'workspace.json')]},root/'progress.json')['results'][0]
    first = run(before)
    monkeypatch.chdir(tmp_path)
    after = tmp_path/'after'
    before.rename(after)
    monkeypatch.chdir(after)
    second = run(after)
    assert second['reused'] and second['key']==first['key']
    assert second['result']['source']['path']==str(after/'subjects.csv')
    assert second['result']['preferences']['ui_recorded']['path']==str(after/'subjects.csv')
    assert second['result']['preferences']['ui_recorded']['label']==str(source)


def test_path_codec_preserves_container_graph_without_editing_live_result(tmp_path, monkeypatch):
    before = tmp_path/'before'
    before.mkdir()
    monkeypatch.chdir(before)
    source = before/'source.csv'
    external = tmp_path/'external.csv'
    array = np.array([1.,np.nan,3.])
    shared = OrderedDict(path=source, label=str(source), external_path=external, array=array)
    values = [shared, shared]
    values.append(values)
    tuple_cycle = (values,)
    values.append(tuple_cycle)
    result = OrderedDict(paths=(str(source),external), nested=values, measurements=array,
                         named=PathAndMeasurements(source,array), cycle=tuple_cycle)
    cache = before/'value.pkl'
    queue._write_grid_value(cache,result)
    assert shared['path']==source and result['paths']==(str(source),external)
    assert shared['array'] is array and values[0] is values[1] and values[2] is values
    # Portable storage must not retain the internal absolute path in path fields.
    # The identical display label is deliberately still absolute.
    monkeypatch.chdir(tmp_path)
    after = tmp_path/'after'
    before.rename(after)
    monkeypatch.chdir(after)
    restored = queue._read_grid_value(after/'value.pkl')
    assert type(restored) is OrderedDict and type(restored['paths']) is tuple
    assert restored['paths']==(str(after/'source.csv'),external)
    assert type(restored['nested'][0]) is OrderedDict
    assert restored['nested'][0]['path']==after/'source.csv'
    assert isinstance(restored['nested'][0]['path'],Path)
    assert restored['nested'][0]['label']==str(source)
    assert restored['nested'][0]['external_path']==external
    assert restored['nested'][0] is restored['nested'][1]
    assert restored['nested'][2] is restored['nested']
    assert restored['nested'][3] is restored['cycle']
    assert restored['cycle'][0] is restored['nested']
    assert type(restored['named']) is PathAndMeasurements
    assert restored['named'].path==after/'source.csv'
    assert restored['named'].measurements is restored['measurements']
    assert restored['nested'][0]['array'] is restored['measurements']
    np.testing.assert_array_equal(restored['measurements'],array)


def test_direct_path_result_moves_with_cache(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    queue._write_grid_value(tmp_path/'direct.pkl',tmp_path/'source.csv')
    restored = queue._read_grid_value(tmp_path/'direct.pkl')
    assert isinstance(restored,Path) and restored==tmp_path/'source.csv'
