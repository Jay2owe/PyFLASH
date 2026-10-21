"""Atomic text/JSON publication for analysis outputs and recovery state."""
import json
import time
import os
from pathlib import Path
import tempfile
from contextlib import contextmanager
from threading import RLock

_revision_lock = RLock()

_WINDOWS = os.name == 'nt'


def read_json(path):
    """Read complete published state, retrying brief Windows sharing failures.

    Five attempts wait at most 75 milliseconds in total. Permanent denial,
    missing files, invalid UTF-8 and malformed JSON remain visible errors.
    This reader never rewrites, repairs or returns cached state.
    """
    path = Path(path)
    for attempt in range(5):
        try:
            content = path.read_text(encoding='utf-8')
        except PermissionError as exc:
            if not _WINDOWS or getattr(exc,'winerror',None) not in {None,5,32,33} or attempt == 4:
                raise
            time.sleep(.005 * 2**attempt)
        else:
            return json.loads(content)



def atomic_replace(temporary, path):
    """Keep complete old bytes while retrying brief Windows access failures.

    Twenty attempts wait at most 6.22 seconds in total. Permanent failures still
    raise, and callers retain ownership of temporary-file cleanup.
    """
    import time
    for attempt in range(20):
        try:
            os.replace(temporary, path)
            return
        except PermissionError as exc:
            if getattr(exc,'winerror',None) not in {5,32,33} or attempt == 19:
                raise
            time.sleep(min(.02 * 2**attempt, .4))


@contextmanager
def atomic_text(path, *, newline=None):
    """Publish complete UTF-8 text while preserving prior bytes on failure."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline=newline) as stream:
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
        atomic_replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def _locked_revision(path):
    """Serialize the final revision check and replacement across processes."""
    with _revision_lock, path.with_suffix(path.suffix + '.lock').open('a+b') as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def code_identity():
    """Fingerprint the installed Python sources, including editable local edits."""
    import hashlib
    root = Path(__file__).parent
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob('*.py'))}


def write_json(path, payload, *, revision_key=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if revision_key is None:
            atomic_replace(temporary, path)
        else:
            revision = payload[revision_key]
            if type(revision) is not int:
                raise ValueError('A persisted revision must be an integer.')
            with _locked_revision(path):
                if path.exists():
                    previous = read_json(path)
                    if previous.get(revision_key, -1) >= revision:
                        return False
                atomic_replace(temporary, path)
        return True
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
