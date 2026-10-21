"""
Pickle-based save/load for Experiment and Batch objects.
"""

import os
import re
import pickle
import tempfile
from pathlib import Path

import pandas as pd

from PyFLASH.config import check_directory
from PyFLASH._logging import logger as _log


LEGACY_IMAGE_CACHE_SUFFIX = ".images.pkl"
_LEGACY_MODULE_ROOT = "IF_analysis"
_CURRENT_MODULE_ROOT = "PyFLASH"
STATE_SCHEMA_VERSION = 2


def _migrate_v0_to_v1(obj):
    obj._state_schema_version = 1


def _migrate_v1_to_v2(obj):
    # Older absolute paths remain supported. A new save records relative paths.
    obj._state_schema_version = 2


def _migrate_state(obj):
    """Stamp legacy states in memory; reject versions this reader cannot handle."""
    current = getattr(obj, "_state_schema_version", 0)
    if type(current) is not int or current < 0 or current > STATE_SCHEMA_VERSION:
        raise ValueError(f"Unsupported analysis state schema version: {current!r}")
    # Version 0 is the historical unversioned Experiment/Batch pickle. Existing
    # array/column migrations below remain responsible for that payload.
    migrations = {0: _migrate_v0_to_v1, 1: _migrate_v1_to_v2}
    while current < STATE_SCHEMA_VERSION:
        migrations[current](obj)
        current += 1
    return obj


def _remap_legacy_module(module):
    """Return the current PyFLASH module path for legacy pickle references."""
    if module == _LEGACY_MODULE_ROOT:
        return _CURRENT_MODULE_ROOT

    legacy_pyflash_prefix = f"{_LEGACY_MODULE_ROOT}.{_CURRENT_MODULE_ROOT}"
    if module == legacy_pyflash_prefix:
        return _CURRENT_MODULE_ROOT
    if module.startswith(f"{legacy_pyflash_prefix}."):
        return f"{_CURRENT_MODULE_ROOT}.{module[len(legacy_pyflash_prefix) + 1:]}"

    legacy_prefix = f"{_LEGACY_MODULE_ROOT}."
    if module.startswith(legacy_prefix):
        return f"{_CURRENT_MODULE_ROOT}.{module[len(legacy_prefix):]}"

    return module


class _PyFLASHUnpickler(pickle.Unpickler):
    """Unpickler that can read caches created before the package rename."""

    def find_class(self, module, name):
        return super().find_class(_remap_legacy_module(module), name)


class _ContentHashReader:
    """Hash every byte consumed by the unpickler, without retaining the file."""
    def __init__(self, raw):
        from hashlib import sha256
        self.raw = raw
        self.digest = sha256()

    def read(self, size=-1):
        content = self.raw.read(size)
        self.digest.update(content)
        return content

    def readline(self, size=-1):
        content = self.raw.readline(size)
        self.digest.update(content)
        return content

    def readinto(self, buffer):
        count = self.raw.readinto(buffer)
        if count:
            self.digest.update(memoryview(buffer)[:count])
        return count


def _read_pickle(filename, with_hash=False):
    with open(filename, "rb") as raw:
        stream = _ContentHashReader(raw) if with_hash else raw
        obj = _PyFLASHUnpickler(stream).load()
        if with_hash:
            while stream.read(1024 * 1024):
                pass
            return obj, stream.digest.hexdigest()
        return obj, None


def _load_pickle(filename):
    return _read_pickle(filename)[0]


def _resolve_existing_path(path):
    """Return an existing equivalent path if possible, else the original path."""
    if not isinstance(path, str) or path.strip() == "":
        return path
    if os.path.exists(path):
        return path
    resolved = check_directory(path)
    return resolved if resolved is not None else path


def _normalize_one_object_paths(obj, verbose=False):
    """
    Rebase an object's root path (`filePath`) and regenerate derived save paths.
    Returns True if any path changed.
    """
    changed = False
    old_path = getattr(obj, "filePath", None)
    if isinstance(old_path, str):
        new_path = _resolve_existing_path(old_path)
        if new_path != old_path:
            setattr(obj, "filePath", new_path)
            changed = True
            if verbose:
                _log.status(f"  Rebased {getattr(obj, 'name', type(obj).__name__)}: {old_path} -> {new_path}")

    file_path = getattr(obj, "filePath", None)
    if isinstance(file_path, str) and os.path.exists(file_path) and hasattr(obj, "createSavePaths"):
        try:
            obj.createSavePaths()
        except Exception as exc:
            if verbose:
                _log.warn(f"Could not refresh save paths for {getattr(obj, 'name', type(obj).__name__)} ({exc})")
    return changed


def _normalize_loaded_paths(obj, verbose=False):
    """
    Normalize paths for a loaded Experiment/Batch and nested experiments.
    """
    changed = _normalize_one_object_paths(obj, verbose=verbose)
    if hasattr(obj, "experiment_list"):
        for exp in getattr(obj, "experiment_list", []):
            changed = _normalize_one_object_paths(exp, verbose=verbose) or changed
    return changed


def _strip_legacy_image_arrays(obj):
    """
    Remove legacy inline image arrays from loaded image tables.

    Returns True if any table was changed.
    """
    changed = False
    targets = [obj]
    if hasattr(obj, "experiment_list"):
        targets.extend(list(getattr(obj, "experiment_list", [])))
    for target in targets:
        image_df = getattr(target, "images", None)
        if isinstance(image_df, pd.DataFrame) and "ImageArray" in image_df.columns:
            target.images = image_df.drop(columns=["ImageArray"]).copy()
            changed = True
    return changed


_OLD_EXP_SUFFIX_RE = re.compile(r"_exp(\d+)$")


def _migrate_exp_suffix_columns(obj):
    """Convert old ``_expN`` column suffixes to ``.expN`` on the batch summary.

    Only applies to Batch objects (those with ``experiment_list``), since
    per-experiment summaries never carry experiment-disambiguation suffixes.

    Returns True if any column was renamed.
    """
    if not hasattr(obj, "experiment_list"):
        return False
    summary = getattr(obj, "summary", None)
    if not isinstance(summary, pd.DataFrame):
        return False
    new_cols = []
    any_renamed = False
    for col in summary.columns:
        new_col = _OLD_EXP_SUFFIX_RE.sub(r".exp\1", str(col))
        new_cols.append(new_col)
        if new_col != str(col):
            any_renamed = True
    if any_renamed:
        obj.summary.columns = new_cols
    return any_renamed


def normalize_paths(obj, verbose=True):
    """
    Public helper: normalize `filePath` + derived save paths in-place.

    Useful if an object is already in memory and not loaded via `load_state`.
    Returns True if any root path was rebased.
    """
    return _normalize_loaded_paths(obj, verbose=verbose)


def save_state(obj, filename=None, verbose=True, *, project_root=None):
    """
    Save an Experiment or Batch to disk.

    Parameters
    ----------
    obj : Experiment or Batch
    filename : str, optional
        Defaults to '{csv_path}/{name}.pkl'
    project_root : path-like, optional
        Root moved with this state. Defaults to the analysis root when the
        destination is inside it; otherwise to the destination's folder.
    """
    if filename is None:
        filename = os.path.join(obj.csv_path, f"{obj.name}.pkl")

    _migrate_state(obj)
    obj._state_path = filename
    sources = list(getattr(obj, "_provenance_sources", []) or [])
    state_source = {
        "path": os.path.abspath(os.fspath(filename)),
        "role": "batch_pickle",
        "project_root": os.path.dirname(os.path.abspath(os.fspath(filename))),
    }
    if state_source not in sources:
        sources.append(state_source)
    obj._provenance_sources = sources
    from PyFLASH._state_paths import SAVE_ROOT
    destination = Path(filename).resolve()
    root = Path(project_root).resolve() if project_root is not None else Path(
        getattr(obj, 'source_root', None) or getattr(obj, 'filePath', None) or destination.parent).resolve()
    if project_root is None and not destination.is_relative_to(root):
        root = destination.parent
    obj._state_path_manifest = {'schema_version': 1,
                                'root_from_state': os.path.relpath(root, destination.parent)}
    from PyFLASH.config import config_snapshot
    from PyFLASH._persistence import code_identity
    from PyFLASH.dependencies import check
    obj._state_environment = {'configuration': config_snapshot(), 'code': code_identity(),
                              'versions': {entry['package']: entry['version'] for entry in check()}}
    from PyFLASH._cache_identity import file_hash
    candidates = {}
    for target in [obj, *list(getattr(obj, 'experiment_list', []) or [])]:
        for source in getattr(target, '_provenance_sources', []) or []:
            if source.get('role') != 'batch_pickle' and source.get('path'):
                candidates[os.fspath(source['path'])] = source.get('role', 'source')
        for path in getattr(target, 'source_paths', []) or []:
            candidates[os.fspath(path)] = 'source'
    obj._state_inputs = [{'path': path, 'role': role,
                          'sha256': file_hash(path) if Path(path).is_file() else None}
                         for path, role in sorted(candidates.items())]
    os.makedirs(os.path.dirname(filename) or ".", exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=os.path.dirname(os.path.abspath(filename)), prefix=".pyflash-state-", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, 'wb') as f:
            token = SAVE_ROOT.set(root)
            try:
                pickle.dump(obj, f, protocol=pickle.HIGHEST_PROTOCOL)
            finally:
                SAVE_ROOT.reset(token)
            f.flush()
            os.fsync(f.fileno())
        from PyFLASH._persistence import atomic_replace
        atomic_replace(temporary, filename)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise

    legacy_cache = f"{filename}{LEGACY_IMAGE_CACHE_SUFFIX}"
    if os.path.exists(legacy_cache):
        os.remove(legacy_cache)

    size_mb = os.path.getsize(filename) / (1024 * 1024)
    if verbose:
        _log.confirm(f"Saved '{obj.name}' to {filename} ({size_mb:.1f} MB)")


def load_state(filename, normalize_paths=True, resave_if_rebased=False, verbose=True, *, resave_if_migrated=True):
    """
    Load an Experiment or Batch from disk.

    Parameters
    ----------
    filename : str
        Path to .pkl file.
    normalize_paths : bool, default True
        Rebase stale absolute paths (e.g. across different usernames/machines)
        using `check_directory`, then refresh derived save paths.
    resave_if_rebased : bool, default False
        If True, overwrite the pickle after path rebasing.
    resave_if_migrated : bool, default True
        Persist historical column/image migrations. Set False for a read-only
        inspection: migrations still run in memory without replacing the source.

    Returns
    -------
    Experiment or Batch
    """
    from PyFLASH._cache_identity import file_hash
    raw, consumed_hash = _read_pickle(filename, with_hash=True)
    if file_hash(filename) != consumed_hash:
        raise RuntimeError("Saved batch changed while loading; retry the request.")
    obj = _restore_loaded_state(raw, filename, normalize_paths, resave_if_rebased,
                                verbose, resave_if_migrated)
    obj._pyflash_resident_input_sha256 = consumed_hash
    return obj


def _restore_loaded_state(obj, filename, normalize_paths, resave_if_rebased,
                          verbose, resave_if_migrated):
    """Apply the existing migration/path logic to one already loaded object."""
    obj = _migrate_state(obj)
    from PyFLASH._state_paths import restore_paths
    portable_rebased = restore_paths(obj, filename)

    obj._state_path = filename
    sources = list(getattr(obj, "_provenance_sources", []) or [])
    state_source = {
        "path": os.path.abspath(os.fspath(filename)),
        "role": "batch_pickle",
        "project_root": os.path.dirname(os.path.abspath(os.fspath(filename))),
    }
    if state_source not in sources:
        sources.append(state_source)
    obj._provenance_sources = sources
    legacy_arrays_removed = _strip_legacy_image_arrays(obj)
    exp_suffix_migrated = _migrate_exp_suffix_columns(obj)
    rebased = portable_rebased
    if normalize_paths:
        rebased = _normalize_loaded_paths(obj, verbose=verbose) or rebased

    legacy_cache = f"{filename}{LEGACY_IMAGE_CACHE_SUFFIX}"
    should_resave = (resave_if_migrated and (legacy_arrays_removed or exp_suffix_migrated or os.path.exists(legacy_cache))) or (rebased and resave_if_rebased)
    if should_resave:
        save_state(obj, filename, verbose=False)

    if verbose:
        _log.confirm(f"Loaded '{obj.name}' from {filename}")
        _log.status(f"  Data keys: {list(obj.data.keys())}")
        _log.status(f"  Summary shape: {obj.summary.shape}")
        if hasattr(obj, 'condition_list'):
            _log.status(f"  Conditions: {[c.name for c in obj.condition_list]}")
    return obj


def _restore_captured_state(snapshot, filename, consumed_sha256):
    """Restore an owned, already hashed snapshot through the ordinary owner.

    Internal callers must own the frozen stream and verify the original file
    again before admitting this object. No paths or migrations are duplicated.
    """
    raw = _PyFLASHUnpickler(snapshot).load()
    batch = _restore_loaded_state(raw, os.fspath(filename), True, False, False, False)
    batch._pyflash_resident_input_sha256 = consumed_sha256
    return batch


def _load_cached_state(filename, cache=None, *, expected_sha256=None, verify_current=True, verbose=True):
    """Verify consumed saved bytes and optionally reuse a resident object.

    Callers skipping the final file check must provide their captured expected
    digest and own a later check before admitting a result.
    """
    if not verify_current and expected_sha256 is None:
        raise ValueError("An expected input hash is required when deferring verification.")
    from PyFLASH._cache_identity import file_hash
    filename = os.fspath(filename)
    if cache is not None and filename in cache:
        current_hash = file_hash(filename)
        if expected_sha256 is not None and current_hash != expected_sha256:
            raise RuntimeError("Saved batch changed while loading; retry the request.")
        batch = cache[filename]
        if getattr(batch, "_pyflash_resident_input_sha256", None) == current_hash:
            return batch
    raw, loaded_hash = _read_pickle(filename, with_hash=True)
    if expected_sha256 is not None and loaded_hash != expected_sha256:
        raise RuntimeError("Saved batch changed while loading; retry the request.")
    batch = _restore_loaded_state(raw, filename, True, False, verbose, False)
    if verify_current and file_hash(filename) != loaded_hash:
        raise RuntimeError("Saved batch changed while loading; retry the request.")
    batch._pyflash_resident_input_sha256 = loaded_hash
    if cache is not None:
        cache[filename] = batch
    return batch
