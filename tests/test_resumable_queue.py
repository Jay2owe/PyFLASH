"""Interrupted registered batches skip only verified completed calls."""
import json
from pathlib import Path
import pytest

from PyFLASH import queue,spec


def setup(tmp_path,monkeypatch,fn,entries=None):
    monkeypatch.setattr(spec,"PLOT_REGISTRY",{"check":"test.check"})
    monkeypatch.setattr(spec,"_resolve_func",lambda name:fn)
    path = tmp_path/"request.json"
    path.write_text(json.dumps({"plots":entries or [{"type":"check","value":i} for i in range(3)]}))
    return path,tmp_path/"progress.json"


def test_queue_continues_after_failure_and_resumes_only_failed_item(tmp_path,monkeypatch):
    calls=[]
    fail=[True]
    def fn(source,value=0):
        calls.append(value)
        if value==1 and fail[0]: raise ValueError("bad item")
        return value*2
    request,progress=setup(tmp_path,monkeypatch,fn)
    first=queue.run_spec_queue("unchanged input",request,progress)
    assert calls==[0,1,2] and first["successes"]==[0,2]
    assert first["failures"][0]["error"]=="ValueError: bad item"
    fail[0]=False
    second=queue.run_spec_queue("unchanged input",request,progress)
    assert calls==[0,1,2,1] and second["successes"]==[0,1,2]
    assert not second["failures"]
    assert len(json.loads(progress.read_text())["items"][1]["attempts"])==2


def test_interrupted_queue_resumes_first_unfinished_item(tmp_path,monkeypatch):
    calls=[]
    def fn(source,value=0):
        calls.append(value)
        if value==1 and len(calls)==2: raise KeyboardInterrupt()
        return value
    request,progress=setup(tmp_path,monkeypatch,fn)
    with pytest.raises(KeyboardInterrupt):queue.run_spec_queue("input",request,progress)
    assert json.loads(progress.read_text())["items"][0]["status"]=="done"
    result=queue.run_spec_queue("input",request,progress)
    assert calls==[0,1,1,2] and result["successes"]==[0,1,2]


def test_unknown_parameter_blocks_whole_queue_before_execution(tmp_path,monkeypatch):
    calls=[]
    def fn(source,value=0):calls.append(value)
    request,progress=setup(tmp_path,monkeypatch,fn,[{"type":"check","value":0},{"type":"check","vaule":1}])
    with pytest.raises(ValueError,match="Unknown parameters: vaule"):
        queue.run_spec_queue("input",request,progress)
    assert not calls and not progress.exists()


def test_missing_later_input_blocks_the_whole_queue_before_any_item(tmp_path,monkeypatch):
    calls = []
    existing = tmp_path/'existing.csv'
    existing.write_text('x\n1\n')
    def fn(source,path=None,filename='output'):
        calls.append(path)
    request,progress = setup(tmp_path,monkeypatch,fn,[
        {'type':'check','path':str(existing),'filename':'output'},
        {'type':'check','path':str(tmp_path/'missing.csv'),'filename':'output'}])
    with pytest.raises(ValueError,match='plots\\[1\\].*Missing input path'):
        queue.run_spec_queue('input',request,progress)
    assert not calls and not progress.exists()


def test_changed_input_and_corrupted_completed_result_are_not_skipped(tmp_path,monkeypatch):
    def fn(source,value=0):return value
    request,progress=setup(tmp_path,monkeypatch,fn)
    queue.run_spec_queue("input",request,progress)
    with pytest.raises(ValueError,match="changed"):
        queue.run_spec_queue("different",request,progress)
    record=json.loads(progress.read_text())
    (progress.parent/record["items"][0]["result"]["path"]).write_bytes(b"corrupt")
    with pytest.raises(ValueError,match="lost an output"):
        queue.run_spec_queue("input",request,progress)


def test_changed_scientific_configuration_is_not_reused(tmp_path,monkeypatch):
    from PyFLASH.config import Config
    def fn(source,value=0):return value
    request,progress=setup(tmp_path,monkeypatch,fn)
    queue.run_spec_queue("input",request,progress)
    monkeypatch.setattr(Config,"EFFECT_CI_RANDOM_STATE",999)
    with pytest.raises(ValueError,match="changed"):
        queue.run_spec_queue("input",request,progress)


def test_queue_owns_separate_outputs_and_can_move_its_result_folder(tmp_path,monkeypatch):
    from types import SimpleNamespace
    original = SimpleNamespace(fig_path='original')
    destinations=[]
    def fn(source,value=0):
        destinations.append(source.fig_path)
        return value
    folder=tmp_path/'before'
    folder.mkdir()
    request,progress=setup(folder,monkeypatch,fn)
    queue.run_spec_queue(original,request,progress)
    assert original.fig_path=='original' and len(set(destinations))==3
    state=json.loads(progress.read_text())
    assert all(not Path(i['result']['path']).is_absolute() for i in state['items'])
    moved=tmp_path/'after'
    folder.rename(moved)
    queue.run_spec_queue(original,moved/request.name,moved/progress.name)
    assert len(destinations)==3


def test_declared_file_bytes_are_recorded_and_changed_input_cannot_resume(tmp_path,monkeypatch):
    path = tmp_path/'measurements.csv'
    path.write_bytes(b'first input bytes')
    calls = []
    def fn(source,path=None):
        calls.append(path)
        return Path(path).read_bytes()
    request,progress = setup(tmp_path,monkeypatch,fn,[{'type':'check','path':str(path)}])
    first = queue.run_spec_queue(None,request,progress)
    assert first['successes']==[0]
    record = json.loads(progress.read_text())
    assert record['items'][0]['input_files'][0]['sha256']==queue._digest_file(path)
    before = progress.read_bytes()
    path.write_bytes(b'changed input bytes')
    with pytest.raises(ValueError,match='changed'):
        queue.run_spec_queue(None,request,progress)
    assert calls==[str(path)] and progress.read_bytes()==before


def test_source_free_queue_assigns_each_default_output_directory(tmp_path,monkeypatch):
    destinations = []
    def fn(source=None,value=0,save_path=None):
        assert save_path is not None
        directory = Path(save_path)
        directory.mkdir(parents=True,exist_ok=True)
        destinations.append(directory)
        # Literal ownership marker, not a scientific figure.
        (directory/'ownership.export-check').write_text(str(value))
        return {'value':value,'path':str(directory/'ownership.export-check')}
    request,progress = setup(tmp_path,monkeypatch,fn)
    first = queue.run_spec_queue(None,request,progress)
    assert first['successes']==[0,1,2] and len(set(destinations))==3
    assert all(path.is_relative_to(progress.parent) for path in destinations)
    assert [int((path/'ownership.export-check').read_text()) for path in destinations]==[0,1,2]
    queue.run_spec_queue(None,request,progress)
    assert len(destinations)==3
    (destinations[0]/'ownership.export-check').write_text('damaged output')
    with pytest.raises(ValueError,match='lost an output'):
        queue.run_spec_queue(None,request,progress)
    assert len(destinations)==3


def test_changed_file_during_execution_retains_failed_attempt(tmp_path,monkeypatch):
    path = tmp_path/'measurements.csv'
    path.write_bytes(b'before')
    def fn(source,path=None):
        Path(path).write_bytes(b'changed while running')
        return 1
    request,progress = setup(tmp_path,monkeypatch,fn,[{'type':'check','path':str(path)}])
    result = queue.run_spec_queue(None,request,progress)
    assert result['successes']==[] and result['failures'][0]['index']==0
    assert 'input' in result['failures'][0]['error'].lower()
    state = json.loads(progress.read_text())
    receipt = progress.parent/state['items'][0]['attempts'][0]['receipt']
    assert receipt.is_file() and json.loads(receipt.read_text())['status']=='failed'


def test_default_output_filename_collision_blocks_before_any_call(tmp_path,monkeypatch):
    calls = []
    def fn(source=None,value=0,save_path=None,save_name='Outcome'):
        calls.append(value)
    request,progress = setup(tmp_path,monkeypatch,fn,[
        {'type':'check','value':1,'save_path':str(tmp_path/'shared')},
        {'type':'check','value':2,'save_path':str(tmp_path/'shared')}])
    with pytest.raises(ValueError,match='output collision'):
        queue.run_spec_queue(None,request,progress)
    assert calls==[] and not progress.exists()


@pytest.mark.parametrize('damage', ['boolean_schema', 'missing_items', 'wrong_index',
                                   'unknown_status', 'invalid_attempts', 'later_damaged_output'])
def test_all_saved_queue_items_are_validated_before_resume_writes(tmp_path, monkeypatch, damage):
    calls = []
    def fn(source, value=0):
        calls.append(value)
        return value
    request, progress = setup(tmp_path, monkeypatch, fn)
    queue.run_spec_queue('input', request, progress)
    state = json.loads(progress.read_text())
    if damage == 'boolean_schema':
        state['schema_version'] = True
    elif damage == 'missing_items':
        state['items'].pop()
    elif damage == 'wrong_index':
        state['items'][1]['index'] = 0
    elif damage == 'unknown_status':
        state['items'][1]['status'] = 'anything'
    elif damage == 'invalid_attempts':
        state['items'][1]['attempts'] = {}
    else:
        # A pending earlier item must not run before a damaged later item is found.
        state['items'][0]['status'] = 'pending'
        target = progress.parent / state['items'][2]['result']['path']
        target.write_bytes(b'damaged')
    progress.write_text(json.dumps(state))
    before = progress.read_bytes()
    summary = progress.with_name('progress-summary.json')
    summary_before = summary.read_bytes()
    calls.clear()
    with pytest.raises(ValueError, match='(?i)(queue|schema|output|items|status|attempt)'):
        queue.run_spec_queue('input', request, progress)
    assert not calls
    assert progress.read_bytes() == before
    assert summary.read_bytes() == summary_before


def test_queue_resumes_declared_inputs_after_project_folder_moves(tmp_path, monkeypatch):
    folder = tmp_path/'project-before'
    folder.mkdir()
    source = folder/'measurements.csv'
    source.write_bytes(b'recorded input')
    calls = []
    def fn(data, path=None):
        calls.append(path)
        return Path(path).read_bytes()
    request, progress = setup(folder, monkeypatch, fn, [{'type':'check', 'path':'measurements.csv'}])
    monkeypatch.chdir(folder)
    queue.run_spec_queue(None, request, progress)
    state = json.loads(progress.read_text())
    assert not Path(state['items'][0]['input_files'][0]['path']).is_absolute()
    monkeypatch.chdir(tmp_path)
    moved = tmp_path/'project-after'
    assert folder.resolve().is_relative_to(tmp_path.resolve()) and moved.resolve().is_relative_to(tmp_path.resolve())
    folder.rename(moved)
    monkeypatch.chdir(moved)
    outcome = queue.run_spec_queue(None, moved/request.name, moved/progress.name)
    assert outcome['successes'] == [0] and calls == ['measurements.csv']


def test_explicit_old_queue_schema_migrates_only_with_matching_scientific_identity(tmp_path, monkeypatch):
    import hashlib
    calls = []
    def fn(data, value=0):
        calls.append(value)
        return value
    request, progress = setup(tmp_path, monkeypatch, fn)
    queue.run_spec_queue(None, request, progress)
    record = json.loads(progress.read_text())
    record['schema_version'] = 1
    record.pop('relative_paths')
    record['identity'] = hashlib.sha256(json.dumps(record['record'], sort_keys=True, default=str).encode()).hexdigest()
    progress.write_text(json.dumps(record))
    before = progress.read_bytes()
    version, migrated = queue._read_queue_record(progress)
    assert version == 1 and migrated['schema_version'] == 2
    assert progress.read_bytes() == before
    calls.clear()
    queue.run_spec_queue(None, request, progress)
    assert not calls and json.loads(progress.read_text())['schema_version'] == 2


@pytest.mark.parametrize('version', [None, False, 3])
def test_queue_record_requires_an_explicit_supported_integer_version(tmp_path, version):
    record = {'schema_version':version}
    path = tmp_path/'record.json'
    path.write_text(json.dumps(record))
    before = path.read_bytes()
    with pytest.raises(ValueError, match='schema version'):
        queue._read_queue_record(path)
    assert path.read_bytes() == before
