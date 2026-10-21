"""Cold snapshots own their bytes, preserve full tables and refuse changes."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from threading import Event
import hashlib
import os
import pickle

import pandas as pd
import pytest
from PyFLASH import _cache_identity, serialization
from PyFLASH.ui import loading, preparation, workspace

EVIDENCE = Path(__file__).resolve().parents[1] / 'reproducibility/reference-sources/consumed-input-guards'


def input_file(tmp_path):
    source = EVIDENCE / 'input-consumption-endpoints-frozen-before-v2/ui-pickle'
    path = tmp_path / 'input.pkl'
    original = (source / 'original-input.bin').read_bytes()
    changed = (source / 'substituted-input.bin').read_bytes()
    path.write_bytes(original)
    return path, original, changed


@pytest.mark.parametrize('fails', [False, True])
def test_only_one_session_captures_and_failure_does_not_duplicate_workers(monkeypatch, fails):
    monkeypatch.setattr(preparation, '_snapshot_claimed', False)
    started, release = Event(), Event()
    calls = []
    expected = object()
    monkeypatch.setattr(preparation, 'prepare_services', lambda: None)
    def capture(path, future):
        calls.append(path)
        started.set()
        assert release.wait(10)
        if fails:
            raise ValueError('retained snapshot failure')
        return expected
    monkeypatch.setattr(preparation, '_capture_initial_pickle', capture)
    try:
        with ThreadPoolExecutor(max_workers=8) as sessions:
            answers = list(sessions.map(lambda _: preparation.prepare_initial_pickle('input.pkl'), range(16)))
        assert started.wait(10)
        futures = [answer for answer in answers if answer is not None]
        assert len(futures) == len(calls) == 1
    finally:
        release.set()
    if fails:
        with pytest.raises(ValueError, match='retained snapshot failure'):
            futures[0].result(timeout=10)
    else:
        assert futures[0].result(timeout=10) is expected
    assert preparation.prepare_initial_pickle('input.pkl') is None


def test_capture_restores_complete_object_once_and_warm_open_reuses_it(tmp_path, monkeypatch):
    path, original, _ = input_file(tmp_path)
    monkeypatch.setattr(preparation, '_snapshot_claimed', False)
    calls = []
    restore = serialization._restore_captured_state
    def observe(*args):
        calls.append(args[0])
        return restore(*args)
    monkeypatch.setattr(serialization, '_restore_captured_state', observe)
    captured = preparation.prepare_initial_pickle(path).result(timeout=30)
    digest = hashlib.sha256(original).hexdigest()
    normal = serialization._load_cached_state(path, expected_sha256=digest, verify_current=False, verbose=False)
    assert pickle.dumps(captured.batch) == pickle.dumps(normal)
    assert captured.path == str(path.resolve()) and captured.sha256 == digest
    assert len(calls) == 1 and calls[0].closed
    loading._source.clear()
    first = loading.open_source({'path': str(path), 'kind': 'pickle'},
        initial_identity={'sha256': digest}, _prepared=captured)
    def forbidden(*args, **kwargs):
        raise AssertionError('Warm cache must not deserialize again')
    monkeypatch.setattr(loading.services, 'open_pickle', forbidden)
    second = loading.open_source({'path': str(path), 'kind': 'pickle'})
    pd.testing.assert_frame_equal(first.summary, second.summary, check_exact=True)
    assert preparation.prepare_initial_pickle(path) is None
    assert path.read_bytes() == original
    loading._source.clear()


@pytest.mark.parametrize('moment', ['capture', 'after-capture', 'catalogue'])
def test_changed_content_with_restored_timestamps_is_refused(tmp_path, monkeypatch, moment):
    path, original, changed = input_file(tmp_path)
    stamp = path.stat()
    monkeypatch.setattr(preparation, '_snapshot_claimed', False)
    def rewrite(content):
        path.write_bytes(content)
        os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    capture = _cache_identity._capture_source
    @contextmanager
    def substituted(source):
        rewrite(changed)
        with capture(source) as owned:
            rewrite(original)
            yield owned
    if moment == 'capture':
        monkeypatch.setattr(_cache_identity, '_capture_source', substituted)
    captured = preparation.prepare_initial_pickle(path).result(timeout=30)
    if moment == 'after-capture':
        rewrite(changed)
    elif moment == 'catalogue':
        catalogue = workspace.measurement_catalogue
        def changed_catalogue(*args):
            answer = catalogue(*args)
            rewrite(changed)
            return answer
        monkeypatch.setattr(workspace, 'measurement_catalogue', changed_catalogue)
    loading._source.clear()
    with pytest.raises(ValueError, match='changed while'):
        loading.open_source({'path': str(path), 'kind': 'pickle'},
            initial_identity={'sha256': captured.sha256}, _prepared=captured)
    assert path.stat().st_mtime_ns == stamp.st_mtime_ns
    loading._source.clear()


@pytest.mark.parametrize('mismatch', ['path', 'hash', 'batch', 'kind'])
def test_snapshot_identity_cannot_be_substituted(tmp_path, monkeypatch, mismatch):
    path, _, _ = input_file(tmp_path)
    monkeypatch.setattr(preparation, '_snapshot_claimed', False)
    captured = preparation.prepare_initial_pickle(path).result(timeout=30)
    identity = {'sha256': captured.sha256}
    source = {'path': str(path), 'kind': 'pickle'}
    if mismatch == 'path': captured = replace(captured, path=str(tmp_path/'other.pkl'))
    if mismatch == 'hash': captured = replace(captured, sha256='wrong hash')
    if mismatch == 'batch': captured.batch._pyflash_resident_input_sha256 = 'wrong hash'
    if mismatch == 'kind': source['kind'] = 'csv'
    with pytest.raises(ValueError, match='does not match'):
        loading.open_source(source, initial_identity=identity, _prepared=captured)


def test_parse_failure_closes_the_owned_snapshot(tmp_path, monkeypatch):
    path = tmp_path/'broken.pkl'
    path.write_bytes(b'not a pickle')
    monkeypatch.setattr(preparation, '_snapshot_claimed', False)
    owned = []
    capture = _cache_identity._capture_source
    @contextmanager
    def observe(source):
        with capture(source) as answer:
            owned.append(answer[0])
            yield answer
    monkeypatch.setattr(_cache_identity, '_capture_source', observe)
    with pytest.raises(pickle.UnpicklingError):
        preparation.prepare_initial_pickle(path).result(timeout=30)
    assert len(owned) == 1 and owned[0].closed and path.read_bytes() == b'not a pickle'
