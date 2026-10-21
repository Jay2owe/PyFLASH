"""Every source change during catalogue work must be refused before admission."""
from pathlib import Path
from threading import Event
import concurrent.futures
import hashlib
import os

import pytest
from PyFLASH.ui import loading, preparation, workspace

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'reproducibility/reference-sources/consumed-input-guards/input-consumption-endpoints-frozen-before-v2/ui-pickle'


@pytest.mark.parametrize('large', [False, True])
@pytest.mark.parametrize('tamper', [False, True])
@pytest.mark.parametrize('use_prepared', [False, True])
def test_source_change_during_catalogue_is_refused_for_every_size_and_opening_mode(
        tmp_path, monkeypatch, large, tamper, use_prepared):
    original = (EVIDENCE / 'original-input.bin').read_bytes()
    changed = (EVIDENCE / 'substituted-input.bin').read_bytes()
    assert hashlib.sha256(original).hexdigest() == 'b630e9c4d93b1b58e00434c3b26d421e6ce7f9f9287538f977f143b6181874f5'
    assert hashlib.sha256(changed).hexdigest() == '1f281a5b212a2ef2b5696374c09a387b29021c276fa16302b616377d0c2b49f3'
    if large:
        original += b'\0' * (8 * 1024**2)
        changed += b'\0' * (8 * 1024**2)
    path = tmp_path / 'input.pkl'
    path.write_bytes(original)
    stamp = path.stat()
    digest = hashlib.sha256(original).hexdigest()
    prepared = None
    if use_prepared:
        monkeypatch.setattr(preparation, '_snapshot_claimed', False)
        prepared = preparation.prepare_initial_pickle(path).result(timeout=30)
        assert prepared.sha256 == digest
    actual_version, actual_catalogue = workspace.source_version, workspace.measurement_catalogue
    actual_executor = concurrent.futures.ThreadPoolExecutor
    scheduled, finished = Event(), Event()
    observed_identities = []

    def tracked_version(source):
        identity = actual_version(source)
        observed_identities.append(identity)
        finished.set()
        return identity

    class ObservedExecutor(actual_executor):
        def submit(self, function, *args, **kwargs):
            if function is tracked_version:
                scheduled.set()
            return super().submit(function, *args, **kwargs)

    def catalogue(*args):
        result = actual_catalogue(*args)
        # Instrument genuine scheduling and reads, without replacing hashing.
        # The original parallel implementation must finish its actual read
        # before this mutation. An after-catalogue implementation reads later.
        if scheduled.is_set():
            assert finished.wait(10)
            assert observed_identities[-1]['sha256'] == digest
        if tamper:
            path.write_bytes(changed)
            os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        return result

    monkeypatch.setattr(workspace, 'source_version', tracked_version)
    monkeypatch.setattr(workspace, 'measurement_catalogue', catalogue)
    monkeypatch.setattr(concurrent.futures, 'ThreadPoolExecutor', ObservedExecutor)
    loading._source.clear()
    options = {'initial_identity': {'sha256': digest}}
    if prepared is not None:
        options['_prepared'] = prepared
    try:
        if tamper:
            with pytest.raises(ValueError, match='changed while'):
                loading.open_source({'path': str(path), 'kind': 'pickle'}, **options)
        else:
            batch = loading.open_source({'path': str(path), 'kind': 'pickle'}, **options)
            assert batch._pyflash_resident_input_sha256 == digest
        assert path.read_bytes() == (changed if tamper else original)
        assert path.stat().st_mtime_ns == stamp.st_mtime_ns
        assert observed_identities
    finally:
        loading._source.clear()
