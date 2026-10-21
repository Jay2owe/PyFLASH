"""A shared startup import cannot duplicate workers or lose import failures."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
import pytest
from PyFLASH.ui import preparation


@pytest.mark.parametrize('fails', [False, True])
def test_multiple_sessions_share_one_bounded_preparation(monkeypatch, fails):
    started, release = Event(), Event()
    calls, lock = [], Lock()
    expected = object()
    def prepare(name):
        with lock:
            calls.append(name)
        started.set()
        assert release.wait(10), 'The test must release its preparation worker.'
        if fails:
            raise ImportError('retained startup failure')
        return expected
    monkeypatch.setattr(preparation, '_services', None)
    monkeypatch.setattr(preparation, 'import_module', prepare)
    try:
        with ThreadPoolExecutor(max_workers=8) as sessions:
            futures = list(sessions.map(lambda _: preparation.prepare_services(), range(16)))
        assert started.wait(10)
        assert all(future is futures[0] for future in futures)
        assert calls == ['PyFLASH.ui.services']
    finally:
        release.set()
    if fails:
        with pytest.raises(ImportError, match='retained startup failure'):
            futures[0].result(timeout=10)
    else:
        assert futures[0].result(timeout=10) is expected
    assert preparation.prepare_services() is futures[0]


def test_source_preparation_rechecks_contents_and_retains_read_errors(tmp_path):
    path = tmp_path/'input.csv'
    path.write_text('first measurements')
    first = preparation.prepare_source_version(path).result(timeout=10)
    stamp = path.stat()
    path.write_text('other measurements')
    import os
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    second = preparation.prepare_source_version(path).result(timeout=10)
    assert first != second
    with pytest.raises(FileNotFoundError):
        preparation.prepare_source_version(tmp_path/'missing.csv').result(timeout=10)
