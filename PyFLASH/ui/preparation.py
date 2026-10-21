"""Prepare mandatory data services alongside the first UI shell, once per process.

Workers never access Streamlit or session preferences. Initial saved-data
preparation owns a bounded frozen input and leaves its admission to the UI.
The page still waits for the result before it opens measurements, so import
errors remain visible through the ordinary recovery error display.
"""
from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
from threading import Lock
from dataclasses import dataclass
from pathlib import Path

_lock = Lock()
_services = None
_snapshot_claimed = False


@dataclass(frozen=True)
class _PreparedPickle:
    path: str
    sha256: str
    batch: object


def _capture_initial_pickle(path, services_future):
    from PyFLASH.ui.performance_trace import record, start
    stage = start()
    from PyFLASH._cache_identity import _capture_source
    with _capture_source(path) as (snapshot, digest):
        record("capture_source_and_hash", stage, bytes=Path(path).stat().st_size)
        stage = start()
        services_future.result()
        record("wait_for_services_import", stage)
        stage = start()
        from PyFLASH.serialization import _restore_captured_state
        batch = _restore_captured_state(snapshot, str(path), digest)
        record("restore_batch_from_snapshot", stage)
    return _PreparedPickle(str(path), digest, batch)


def prepare_initial_pickle(path):
    """Capture once per process while imports run; later opens use the cache.

    Only the requesting session retains the future or batch. The shared claim
    prevents concurrent cold sessions from creating duplicate large snapshots.
    """
    global _snapshot_claimed
    path = Path(path).resolve()
    with _lock:
        if _snapshot_claimed:
            return None
        _snapshot_claimed = True
    services_future = prepare_services()
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='pyflash-ui-snapshot')
    future = executor.submit(_capture_initial_pickle, path, services_future)
    executor.shutdown(wait=False)
    return future


def prepare_services():
    """Return the one bounded import future shared by all browser sessions."""
    global _services
    with _lock:
        if _services is None:
            executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='pyflash-ui-import')
            _services = executor.submit(import_module, 'PyFLASH.ui.services')
            # No more work is submitted. The single worker leaves as soon as
            # its import finishes; the future retains its answer or exception.
            executor.shutdown(wait=False)
        return _services


def prepare_source_version(path):
    """Hash a declared source while the shell and mandatory imports proceed."""
    from PyFLASH.ui.workspace import source_version
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='pyflash-ui-source')
    future = executor.submit(source_version, path)
    executor.shutdown(wait=False)
    return future
