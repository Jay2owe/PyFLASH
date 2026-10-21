"""Brief Windows state-file sharing failures do not lose complete job state."""
from pathlib import Path
import hashlib
import json
from types import SimpleNamespace
import pytest
from PyFLASH import _persistence as P
from PyFLASH.ui import workspace


@pytest.mark.parametrize('code',[None,5,32,33])
def test_transient_windows_permission_failure_reads_complete_operation(code,tmp_path,monkeypatch):
    path=tmp_path/'state.json'
    payload={'schema_version':2,'relative_paths':[],'status':'running','id':'original','progress':17}
    P.write_json(path,payload);before=path.read_bytes();read=Path.read_text;attempts=[];waits=[]
    error=PermissionError(13,'temporary sharing failure',str(path))
    if code is not None:error.winerror=code
    def intermittent(current,*args,**kwargs):
        if current==path:
            attempts.append(current)
            if len(attempts)<3:raise error
        return read(current,*args,**kwargs)
    monkeypatch.setattr(P,'_WINDOWS',True);monkeypatch.setattr(Path,'read_text',intermittent)
    monkeypatch.setattr(P,'time',SimpleNamespace(sleep=waits.append))
    assert workspace.read_operation_state(path)==payload
    assert len(attempts)==3 and waits==[.005,.01]
    assert path.read_bytes()==before


def test_permanent_denial_is_bounded_and_preserves_original_exception(tmp_path,monkeypatch):
    path=tmp_path/'state.json';path.write_text('{"status":"old"}',encoding='utf-8');before=path.read_bytes()
    error=PermissionError(13,'permanent access denied',str(path));attempts=[];waits=[]
    def denied(*args,**kwargs):attempts.append(1);raise error
    monkeypatch.setattr(P,'_WINDOWS',True);monkeypatch.setattr(Path,'read_text',denied)
    monkeypatch.setattr(P,'time',SimpleNamespace(sleep=waits.append))
    with pytest.raises(PermissionError) as caught:P.read_json(path)
    assert caught.value is error and len(attempts)==5 and sum(waits)==pytest.approx(.075)
    assert path.read_bytes()==before


@pytest.mark.parametrize('windows,code',[(False,None),(True,123)])
def test_other_permission_failures_are_not_retried(windows,code,tmp_path,monkeypatch):
    error=PermissionError(13,'not a Windows sharing failure');attempts=[]
    if code is not None:error.winerror=code
    def denied(*args,**kwargs):attempts.append(1);raise error
    monkeypatch.setattr(P,'_WINDOWS',windows);monkeypatch.setattr(Path,'read_text',denied)
    monkeypatch.setattr(P,'time',SimpleNamespace(sleep=lambda _:pytest.fail('Unexpected retry')))
    with pytest.raises(PermissionError) as caught:P.read_json(tmp_path/'state.json')
    assert caught.value is error and len(attempts)==1


@pytest.mark.parametrize('content',[b'{broken',b'\xff'])
def test_corrupt_or_non_utf8_state_is_never_retried_or_repaired(content,tmp_path,monkeypatch):
    path=tmp_path/'state.json';path.write_bytes(content)
    monkeypatch.setattr(P,'time',SimpleNamespace(sleep=lambda _:pytest.fail('Unexpected retry')))
    with pytest.raises((json.JSONDecodeError,UnicodeDecodeError)):P.read_json(path)
    assert path.read_bytes()==content


def test_missing_state_and_future_version_remain_errors(tmp_path,monkeypatch):
    monkeypatch.setattr(P,'time',SimpleNamespace(sleep=lambda _:pytest.fail('Unexpected retry')))
    with pytest.raises(FileNotFoundError):P.read_json(tmp_path/'missing.json')
    path=tmp_path/'future.json';P.write_json(path,{'schema_version':999,'status':'running'})
    with pytest.raises(ValueError,match='unsupported version'):workspace.read_operation_state(path)
