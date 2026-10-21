"""Resident input identity, complete data compatibility and replacement races."""
from pathlib import Path
import hashlib,json,os,pickle,shutil
import pandas as pd
import pytest
from PyFLASH import serialization as state

EVIDENCE=Path(__file__).resolve().parents[1]/'reproducibility/reference-sources/resident-input-cache'

def evidence():
    receipt=json.loads((EVIDENCE/'before/frozen-before.json').read_text(encoding='utf-8'))
    for name,digest in receipt['source_manifest'].items():
        assert hashlib.sha256((EVIDENCE/'before'/name).read_bytes()).hexdigest()==digest
    return receipt

@pytest.mark.parametrize('index',range(4))
def test_changed_input_refreshes_complete_table_with_preserved_mtime(tmp_path,index):
    case=evidence()['rows'][index];path=tmp_path/'input.pkl';cache={}
    shutil.copyfile(EVIDENCE/'before'/case['original_input'],path)
    first=state._load_cached_state(path,cache);stamp=path.stat()
    shutil.copyfile(EVIDENCE/'before'/case['current_input'],path)
    os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
    current=state._load_cached_state(path,cache)
    fresh=state.load_state(path,resave_if_migrated=False)
    pd.testing.assert_frame_equal(current.summary,fresh.summary,check_exact=True)
    assert list(cache)==[str(path)]
    assert path.stat().st_mtime_ns==stamp.st_mtime_ns
    if case['original_input_sha256']!=case['current_input_sha256']:assert current is not first

def test_numeric_only_replacement_uses_all_supplied_measurements(tmp_path):
    root=EVIDENCE/'numeric-only';receipt=json.loads((root/'frozen-before.json').read_text(encoding='utf-8'))
    for name,digest in receipt['source_manifest'].items():
        assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest
    path=tmp_path/'input.pkl';cache={};shutil.copyfile(root/'original.pkl',path)
    first=state._load_cached_state(path,cache);shutil.copyfile(root/'current.pkl',path)
    current=state._load_cached_state(path,cache)
    assert current is not first
    actual=current.summary.set_index('AnimalName')['Probe_MeanIntensity'].to_dict()
    assert actual==receipt['literal_expected_values']

def test_warm_cache_reads_once_and_keeps_only_input_path(tmp_path,monkeypatch):
    case=evidence()['rows'][0];path=tmp_path/'input.pkl'
    shutil.copyfile(EVIDENCE/'before'/case['original_input'],path)
    read=state._read_pickle;calls=[]
    def observe(*args,**kwargs):calls.append(kwargs);return read(*args,**kwargs)
    monkeypatch.setattr(state,'_read_pickle',observe)
    cache={};first=state._load_cached_state(path,cache)
    assert state._load_cached_state(path,cache) is first
    assert calls==[{'with_hash':True}] and list(cache)==[str(path)]

def test_legacy_cache_and_uncached_loading_are_read_only(tmp_path):
    case=evidence()['rows'][0];path=tmp_path/'input.pkl'
    shutil.copyfile(EVIDENCE/'before'/case['current_input'],path);original=path.read_bytes()
    cache={str(path):object(),'sentinel':'unchanged'}
    current=state._load_cached_state(path,cache)
    fresh=state._load_cached_state(path,None)
    pd.testing.assert_frame_equal(current.summary,fresh.summary,check_exact=True)
    assert cache['sentinel']=='unchanged' and path.read_bytes()==original

@pytest.mark.parametrize('restore',(False,True))
def test_replacement_during_read_refuses_and_preserves_cache(tmp_path,monkeypatch,restore):
    case=evidence()['rows'][0];path=tmp_path/'input.pkl'
    original=(EVIDENCE/'before'/case['original_input']).read_bytes()
    changed=(EVIDENCE/'before'/case['current_input']).read_bytes()
    path.write_bytes(original);read=state._read_pickle;cache={'sentinel':object()};previous=dict(cache)
    def replace(*args,**kwargs):
        if restore:
            path.write_bytes(changed);answer=read(*args,**kwargs);path.write_bytes(original)
        else:
            answer=read(*args,**kwargs);path.write_bytes(changed)
        return answer
    monkeypatch.setattr(state,'_read_pickle',replace)
    with pytest.raises(RuntimeError,match='changed while loading'):state._load_cached_state(path,cache)
    assert cache==previous

def test_corrupt_replacement_never_returns_stale_batch(tmp_path):
    case=evidence()['rows'][0];path=tmp_path/'input.pkl'
    shutil.copyfile(EVIDENCE/'before'/case['original_input'],path);cache={}
    state._load_cached_state(path,cache);previous=dict(cache);path.write_bytes(b'not a pickle')
    with pytest.raises(pickle.UnpicklingError):state._load_cached_state(path,cache)
    assert cache==previous

@pytest.mark.parametrize('protocol',range(pickle.HIGHEST_PROTOCOL+1))
def test_hash_matches_all_consumed_and_trailing_bytes(tmp_path,protocol):
    value={'protocol':protocol,'values':[None,0,1.25,'text',True]};path=tmp_path/'value.pkl'
    path.write_bytes(pickle.dumps(value,protocol=protocol)+b' trailing bytes')
    actual,digest=state._read_pickle(path,with_hash=True)
    assert actual==value and digest==hashlib.sha256(path.read_bytes()).hexdigest()
