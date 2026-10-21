"""Brief Windows sharing failures must preserve and then atomically replace state."""
import json
import os
import pickle
from types import SimpleNamespace
import pytest
from PyFLASH import _persistence, serialization, queue


def writer(kind,path,value):
    if kind == 'json':
        _persistence.write_json(path,{'value':value})
    elif kind == 'state':
        serialization.save_state(SimpleNamespace(value=value),path,verbose=False)
    else:
        queue._write_pickle(path,{'value':value})


@pytest.mark.parametrize('kind',['json','state','queue'])
def test_transient_windows_failure_retries_same_complete_temporary_file(tmp_path,monkeypatch,kind):
    path = tmp_path/'state'
    writer(kind,path,1)
    original = path.read_bytes()
    replace = os.replace
    attempts = []
    def busy_once(source,target):
        attempts.append(str(source))
        if len(attempts) == 1:
            assert path.read_bytes() == original
            error = PermissionError('transient sharing failure')
            error.winerror = 5
            raise error
        assert path.read_bytes() == original
        return replace(source,target)
    monkeypatch.setattr(os,'replace',busy_once)
    writer(kind,path,2)
    assert len(attempts) == 2 and attempts[0] == attempts[1]
    restored = json.loads(path.read_text()) if kind == 'json' else pickle.loads(path.read_bytes())
    assert (restored['value'] if isinstance(restored,dict) else restored.value) == 2
    assert not list(tmp_path.glob('*.tmp'))


@pytest.mark.parametrize('kind',['json','state','queue'])
def test_permanent_failure_remains_visible_and_preserves_old_bytes(tmp_path,monkeypatch,kind):
    path = tmp_path/'state'
    writer(kind,path,1)
    original = path.read_bytes()
    attempts = []
    def unavailable(*args):
        attempts.append(args)
        error = PermissionError('still unavailable')
        error.winerror = 32
        raise error
    monkeypatch.setattr(os,'replace',unavailable)
    delays = []
    monkeypatch.setattr(_persistence.time, 'sleep', delays.append)
    with pytest.raises(PermissionError,match='still unavailable'):
        writer(kind,path,2)
    assert len(attempts) == 20
    assert sum(delays) == pytest.approx(6.22)
    assert path.read_bytes() == original
    assert not list(tmp_path.glob('*.tmp'))


@pytest.mark.skipif(os.name != 'nt', reason='Native Windows delete-sharing lock')
def test_native_reader_lock_longer_than_old_retry_window_is_recovered(tmp_path):
    import ctypes
    from ctypes import wintypes
    import threading
    path = tmp_path / 'receipt.json'
    _persistence.write_json(path, {'value': 1})
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
        wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.CreateFileW(str(path), 0x80000000, 3, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    release = threading.Timer(.9, kernel.CloseHandle, args=(handle,))
    release.start()
    try:
        _persistence.write_json(path, {'value': 2})
    finally:
        release.join()
    assert json.loads(path.read_text()) == {'value': 2}
    assert not list(tmp_path.glob('*.tmp'))
