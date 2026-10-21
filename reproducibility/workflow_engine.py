"""Standard-library mechanics for scoped, content-verified verification.

Project adapters own scientific assertions and dependency declarations. This
module never approves expected answers, changes tolerances or publishes work.
"""
from __future__ import annotations

from copy import deepcopy
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import sys
import time
import traceback
from uuid import uuid4

SCHEMA = 1
_CAPTURE = ContextVar('verification_reads', default=None)
_AUDIT_INSTALLED = False


def _audit_reads(event, arguments):
    capture = _CAPTURE.get()
    if capture is None or capture.busy or event not in {'open', 'os.scandir', 'os.listdir'}:
        return
    name = arguments[0]
    if not isinstance(name, (str, bytes, os.PathLike)):
        return
    if event == 'open' and (arguments[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT)):
        return
    capture.busy = True
    try:
        path = Path(os.fsdecode(name)).resolve()
        relative = path.relative_to(capture.root).as_posix()
        if event == 'open' and relative not in capture.files:
            capture.files[relative] = digest_file(path) if path.is_file() else None
        elif event != 'open' and relative not in capture.directories:
            capture.directories[relative] = sorted(p.name for p in path.iterdir()) if path.is_dir() else None
    except (ValueError, OSError):
        pass
    finally:
        capture.busy = False


class ReadCapture:
    """Discover exact read dependencies, including missing files and listings."""
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.files, self.directories, self.busy = {}, {}, False

    def __enter__(self):
        global _AUDIT_INSTALLED
        if not _AUDIT_INSTALLED:
            sys.addaudithook(_audit_reads)
            _AUDIT_INSTALLED = True
        self.token = _CAPTURE.set(self)
        return self

    def __exit__(self, *args):
        _CAPTURE.reset(self.token)

    def unchanged(self):
        files, directories = dependency_identity(self.root, self.files, self.directories)
        return files == self.files and directories == self.directories


def dependency_identity(root, files, directories=()):
    root = Path(root).resolve()
    def owned(name):
        path = (root / name).resolve()
        path.relative_to(root)
        return path
    return ({name: digest_file(owned(name)) if owned(name).is_file() else None for name in files},
            {name: sorted(p.name for p in owned(name).iterdir()) if owned(name).is_dir() else None
             for name in directories})


def digest_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def digest_value(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, allow_nan=False, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        # Synced Windows folders can temporarily hold the destination open.
        for attempt in range(6):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(.025 * 2 ** attempt)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def source_identity(root, paths):
    root = Path(root).resolve()
    return {Path(path).resolve().relative_to(root).as_posix(): digest_file(path)
            for path in sorted(set(map(Path, paths))) if path.is_file()}


def preflight(output, required_bytes=0, required_commands=()):
    """Read-only admission; do not install dependencies or create empty folders."""
    output = Path(output).resolve()
    existing = next(path for path in (output, *output.parents) if path.exists())
    free = shutil.disk_usage(existing).free
    missing = [command for command in required_commands if shutil.which(command) is None]
    errors = ([f'Need {required_bytes} bytes; {free} available'] if free < required_bytes else [])
    errors.extend('Missing executable: ' + command for command in missing)
    return {'schema_version': SCHEMA, 'passed': not errors, 'errors': errors,
            'free_bytes': free, 'required_bytes': required_bytes, 'output': str(output)}


@dataclass(frozen=True)
class Stage:
    name: str
    inputs: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    always: bool = False


def select_stages(stages, changed=None, requested=None):
    """Conservative glob declarations plus transitive consumer invalidation."""
    from fnmatch import fnmatchcase
    definitions = {stage.name: stage for stage in stages}
    if len(definitions) != len(stages):
        raise ValueError('Duplicate stage name')
    for stage in stages:
        if set(stage.dependencies) - definitions.keys():
            raise ValueError('Unknown dependency for ' + stage.name)
    visiting, visited = set(), set()
    def visit(name):
        if name in visiting:
            raise ValueError('Cyclic stage dependencies')
        if name not in visited:
            visiting.add(name)
            for dependency in definitions[name].dependencies:
                visit(dependency)
            visiting.remove(name)
            visited.add(name)
    for name in definitions:
        visit(name)
    reasons = {}
    def add(name, reason):
        reasons.setdefault(name, [])
        if reason not in reasons[name]:
            reasons[name].append(reason)
    if requested is not None:
        unknown = set(requested) - definitions.keys()
        if unknown:
            raise ValueError('Unknown requested stages: ' + ', '.join(sorted(unknown)))
        for name in requested:
            add(name, 'explicit request')
    elif changed is None:
        for name in definitions:
            add(name, 'complete declared stage set')
    unknown_paths = []
    for path in changed or ():
        path = str(path).replace('\\', '/')
        matched = [stage.name for stage in stages if any(fnmatchcase(path, pattern) for pattern in stage.inputs)]
        if not matched:
            unknown_paths.append(path)
            for name in definitions:
                add(name, 'unclassified changed path: ' + path)
        for name in matched:
            add(name, 'changed input: ' + path)
    for stage in stages:
        if stage.always:
            add(stage.name, 'always-run guard')
    while True:
        before = set(reasons)
        for stage in stages:
            for dependency in stage.dependencies:
                if stage.name in reasons:
                    add(dependency, 'prerequisite of ' + stage.name)
                # Narrow explicit requests include prerequisites, not unrelated consumers.
                if changed is not None and dependency in reasons:
                    add(stage.name, 'affected consumer of ' + dependency)
        if before == set(reasons):
            break
    return {'schema_version': SCHEMA, 'selected': [s.name for s in stages if s.name in reasons],
            'reasons': reasons, 'unclassified_paths': unknown_paths,
            'scope': 'complete' if changed is None and requested is None else 'focused'}


class MetadataCache:
    """One in-memory metadata entry; bounded disposable JSON disk entries."""
    def __init__(self, directory, max_entries=4, max_bytes=32 * 1024 ** 2):
        self.directory = Path(directory)
        self.max_entries, self.max_bytes = max_entries, max_bytes
        self._key, self._value = None, None

    def get(self, identity, build, current_identity=None):
        key = digest_value({'schema_version': SCHEMA, 'identity': identity})
        if key == self._key:
            return deepcopy(self._value), 'memory'
        path = self.directory / (key + '.json')
        value, origin = None, 'built'
        try:
            if path.stat().st_size <= self.max_bytes:
                stored = json.loads(path.read_text(encoding='utf-8'))
                if type(stored['schema_version']) is int and stored['schema_version'] == SCHEMA and digest_value(stored['identity']) == digest_value(identity) and stored['sha256'] == digest_value(stored['value']):
                    value, origin = stored['value'], 'disk'
        except (OSError, ValueError, KeyError, TypeError):
            pass
        if value is None:
            value = build()
        if current_identity is not None and current_identity() != identity:
            raise RuntimeError('Metadata sources changed while preparing verification')
        stored = {'schema_version': SCHEMA, 'identity': identity,
                  'sha256': digest_value(value), 'value': value}
        encoded_size = len(json.dumps(stored, ensure_ascii=False).encode('utf-8'))
        if origin == 'built' and encoded_size <= self.max_bytes:
            try:
                atomic_json(path, stored)
                entries = sorted(self.directory.glob('*.json'), key=lambda p: p.stat().st_mtime_ns, reverse=True)
                total = 0
                for index, entry in enumerate(entries):
                    total += entry.stat().st_size
                    if index >= self.max_entries or total > self.max_bytes:
                        entry.unlink()
            except OSError:
                pass  # A disposable metadata-cache write cannot lose valid work.
        self._key, self._value = key, deepcopy(value)
        return deepcopy(value), origin


def _owned_file(directory, name):
    original = Path(directory) / name
    if original.is_symlink():
        raise ValueError('Evidence must not be a symlink')
    path = original.resolve()
    path.relative_to(Path(directory).resolve())
    if path.is_symlink():
        raise ValueError('Evidence must not be a symlink')
    return path


def verify_receipt(directory, identity):
    """Return a verified receipt or an explicit reason for refusing reuse."""
    directory = Path(directory)
    try:
        receipt = json.loads((directory / 'receipt.json').read_text(encoding='utf-8'))
        if type(receipt['schema_version']) is not int or receipt['schema_version'] != SCHEMA or digest_value(receipt['identity']) != digest_value(identity):
            return None, 'identity changed'
        if receipt['status'] != 'completed' or receipt['passed'] is not True:
            return None, 'incomplete or failed evidence'
        if not receipt['artifacts']:
            return None, 'missing evidence artifacts'
        for artifact in receipt['artifacts']:
            path = _owned_file(directory, artifact['path'])
            if not path.is_file() or digest_file(path) != artifact['sha256']:
                return None, 'missing or changed artifact: ' + artifact['path']
        if 'result.json' not in {a['path'] for a in receipt['artifacts']}:
            return None, 'missing result identity'
        return receipt, 'verified'
    except (OSError, ValueError, KeyError, TypeError):
        return None, 'missing, corrupt or incompatible receipt'


class Runner:
    """Append attempts; resume only completed, passing, content-verified evidence."""
    def __init__(self, output, identity, resume=False, previous=None):
        self.output, self.identity, self.resume = Path(output), deepcopy(identity), resume
        self.previous = Path(previous) if previous is not None else self.output
        self.records = []

    def run(self, name, action, *, dependencies=(), fresh=False, passing=None, current_identity=None):
        if not name or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in name):
            raise ValueError('Invalid stage name')
        identity = {'run': self.identity, 'stage': name, 'dependencies': list(dependencies)}
        stage = self.output / 'stages' / name
        reason = 'fresh execution requested' if fresh else 'no verified previous attempt'
        previous = self.previous / 'stages' / name
        if self.resume and not fresh and previous.exists():
            for attempt in sorted(previous.iterdir(), reverse=True):
                receipt, reason = verify_receipt(attempt, identity)
                if receipt is not None:
                    result = json.loads((attempt / 'result.json').read_text(encoding='utf-8'))
                    record = dict(receipt, reused=True, original_receipt=str(attempt / 'receipt.json'))
                    self.records.append(record)
                    atomic_json(self.output / 'progress.json', self.records)
                    return result
        output = stage / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid4().hex[:8])
        output.mkdir(parents=True, exist_ok=False)
        record = {'schema_version': SCHEMA, 'name': name, 'identity': identity,
                  'status': 'running', 'passed': False, 'reused': False, 'artifacts': [],
                  'reason': reason, 'owner_pid': os.getpid(), 'directory': str(output)}
        self.records.append(record)
        atomic_json(output / 'receipt.json', record)
        atomic_json(self.output / 'progress.json', self.records)
        started = time.perf_counter()
        try:
            result = action(output)
            if current_identity is not None and current_identity() != self.identity:
                raise RuntimeError('Verification sources changed during stage execution')
            atomic_json(output / 'result.json', result)
            record.update(status='completed', passed=bool(passing(result)) if passing else True,
                          artifacts=[{'path': p.relative_to(output).as_posix(), 'sha256': digest_file(p)}
                                     for p in sorted(output.rglob('*')) if p.is_file() and p != output / 'receipt.json'])
        except BaseException as error:
            record.update(status='interrupted' if not isinstance(error, Exception) else 'failed',
                          error=type(error).__name__ + ': ' + str(error), traceback=traceback.format_exc())
            raise
        finally:
            record['elapsed_seconds'] = time.perf_counter() - started
            atomic_json(output / 'receipt.json', record)
            atomic_json(self.output / 'progress.json', self.records)
        return result

    def summary(self, required, scope='focused'):
        latest = {record['name']: record for record in self.records}
        missing = sorted(set(required) - latest.keys())
        failed = sorted(name for name in required if name in latest and not latest[name]['passed'])
        result = {'schema_version': SCHEMA, 'scope': scope, 'required': list(required),
                  'missing': missing, 'failed': failed, 'passed': bool(required) and not missing and not failed,
                  'complete': scope == 'complete' and bool(required) and not missing and not failed,
                  'fresh': sum(not r['reused'] for r in self.records),
                  'reused': sum(r['reused'] for r in self.records), 'stages': self.records}
        atomic_json(self.output / 'summary.json', result)
        return result
