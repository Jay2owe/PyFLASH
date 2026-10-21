"""
Shared run-folder / manifest I/O for the analysis pipelines.

Every pipeline (``correlation``, ``adjusted_correlation``, ``data_overview``)
writes into a versioned run folder under ``Python Figures/<Pipeline Name>/``.
Figures, generated CSVs, ``manifest.json``, and the shared ``_runs_index.csv``
live under that same pipeline folder so each run's plot files and data files stay
together. That plumbing used to be triplicated (one ``run_dirs`` /
``slug`` / ``append_runs_index`` per pipeline, each hardcoding its folder name and
one of them silently missing). This module is the single, pipeline-name-parameterised
implementation; the pipeline modules pass their folder name and a payload/row.

Pure I/O + stdlib + pandas, so it imports cheaply from anywhere (no plotting,
no scipy). Windows extended-length (``\\?\\``) paths are handled throughout so a
deep Dropbox path can't break a write or an ``isdir`` check.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil

import pandas as pd

from PyFLASH.utils import strip_name

VALID_IF_EXISTS = ("overwrite", "version", "error", "skip")


# ── path primitives (Windows long-path safe) ─────────────────────────────────
def windows_extended_path(path):
    """Return a Windows extended-length path; no-op on other platforms."""
    if os.name != "nt":
        return path
    abs_path = os.path.abspath(path)
    if abs_path.startswith("\\\\?\\"):
        return abs_path
    if abs_path.startswith("\\\\"):
        return "\\\\?\\UNC\\" + abs_path.lstrip("\\")
    return "\\\\?\\" + abs_path


def makedirs(path):
    if path:
        os.makedirs(windows_extended_path(path), exist_ok=True)


def isfile(path):
    return os.path.isfile(windows_extended_path(path))


def isdir(path):
    return os.path.isdir(windows_extended_path(path))


def clear_run_dir(path, base):
    """Remove one generated run directory, guarding against broad deletes."""
    if not path or not isdir(path):
        return
    path_abs = os.path.abspath(path)
    base_abs = os.path.abspath(base)
    try:
        common = os.path.commonpath([path_abs, base_abs])
    except ValueError as exc:
        raise RuntimeError(
            f"Refusing to clear run folder outside {base_abs!r}: {path_abs!r}") from exc
    if common != base_abs or path_abs == base_abs:
        raise RuntimeError(
            f"Refusing to clear run folder outside {base_abs!r}: {path_abs!r}")
    shutil.rmtree(windows_extended_path(path))


def to_csv(frame, path, **kwargs):
    makedirs(os.path.dirname(path) or ".")
    frame.to_csv(windows_extended_path(path), **kwargs)


def write_json(payload, path):
    makedirs(os.path.dirname(path) or ".")
    from PyFLASH._persistence import atomic_text
    with atomic_text(windows_extended_path(path)) as fh:
        json.dump(payload, fh, indent=2, default=str)


def read_json(path):
    with open(windows_extended_path(path), "r", encoding="utf-8") as fh:
        return json.load(fh)


def sha256_file(path, *, chunk=1 << 20, max_bytes=None):
    """Streaming SHA256 of a file (hex), or ``None`` if it can't be hashed.

    Reads in ``chunk``-sized blocks so a large pickle isn't slurped into memory.
    Returns ``None`` (never raises) when the path is missing/unreadable or, when
    ``max_bytes`` is set, larger than that cap — callers record the reason so
    provenance stays best-effort and never breaks a run.
    """
    try:
        p = windows_extended_path(path)
        if max_bytes is not None and os.path.getsize(p) > int(max_bytes):
            return None
        h = hashlib.sha256()
        with open(p, "rb") as fh:
            for block in iter(lambda: fh.read(chunk), b""):
                h.update(block)
        return h.hexdigest()
    except Exception:
        return None


def output_identity(directory, *, exclude=("manifest.json",)):
    """Hash generated run files by relative path; fail if a file is unreadable."""
    from pathlib import Path
    root = Path(windows_extended_path(directory))
    from PyFLASH._cache_identity import file_hash
    return {path.relative_to(root).as_posix(): file_hash(path)
            for path in sorted(root.rglob('*'))
            if path.is_file() and path.relative_to(root).as_posix() not in exclude}


def verify_cached_run(cached, identity, directory):
    """Reject unverified, mismatched or damaged saved results without rewriting."""
    if cached.get('completion_status') != 'complete':
        raise ValueError("Cannot reuse this saved run: its outputs are not complete. "
                         "Wait for the active run or use if_exists='version'.")
    if not identity.get('reusable') or cached.get('request_identity') != identity:
        raise ValueError(
            "Cannot reuse this saved run: inputs, settings or software do not "
            "match a verified request. Use if_exists='version' to preserve it "
            "and compute a new run.")
    expected = cached.get('output_sha256')
    actual = output_identity(directory)
    if not expected or actual != expected:
        raise ValueError(
            "Cannot reuse this saved run: output files are missing or changed. "
            "Use if_exists='version' to preserve it and compute a new run.")


RUN_PATH_KEYS = ('fig_dir', 'data_dir', 'adjusted_means_dir', 'montage')


def write_run_record(manifest, directory):
    """Publish a run manifest with versioned paths relative to its own folder."""
    payload = dict(manifest)
    already_relative = payload.get('path_schema_version') == 1
    for key in RUN_PATH_KEYS:
        value = payload.get(key)
        if value is None:
            continue
        if not already_relative or os.path.isabs(value):
            payload[key] = os.path.relpath(os.path.abspath(value), os.path.abspath(directory))
    payload['path_schema_version'] = 1
    write_json(payload, os.path.join(directory, 'manifest.json'))


def resolve_run_record(manifest, directory):
    """Resolve a verified portable record at its current output-folder location."""
    if manifest.get('path_schema_version') != 1:
        raise ValueError('Cannot reuse this saved run: its path schema is unverified.')
    root = os.path.abspath(directory)
    resolved = dict(manifest)
    for key in RUN_PATH_KEYS:
        value = resolved.get(key)
        if value is None:
            continue
        path = os.path.abspath(os.path.join(root, value))
        if os.path.isabs(value) or os.path.commonpath([root, path]) != root:
            raise ValueError('Cannot reuse this saved run: an output path escapes its folder.')
        resolved[key] = path
    return resolved


def finalize_run_record(result):
    """Publish complete output identities after outer figure collectors finish.

    Only a fresh verified-record producer may update its own manifest. Never
    bless cached results or replace a record another request has published.
    """
    if not isinstance(result, dict) or result.get('reused') or result.get('queued'):
        return
    identity = result.get('request_identity')
    directory = result.get('data_dir')
    if identity is None or not directory or 'output_sha256' not in result:
        return
    path = os.path.join(directory, 'manifest.json')
    if not isfile(path):
        return
    manifest = read_json(path)
    if manifest.get('request_identity') != identity:
        raise RuntimeError('Saved run record changed while finishing its figures.')
    manifest['output_sha256'] = output_identity(directory)
    manifest['completion_status'] = 'partial' if result.get('montage_error') else 'complete'
    if result.get('montage_error'):
        manifest['montage_error'] = result['montage_error']
    if result.get('montage'):
        manifest['montage'] = result['montage']
    write_run_record(manifest, directory)
    result['output_sha256'] = manifest['output_sha256']
    result['completion_status'] = manifest['completion_status']


# ── run-folder resolution ────────────────────────────────────────────────────
def data_root(experiment):
    """Resolve the root for generated pipeline tables.

    Prefer the figure root so CSVs and manifests are co-located with their SVGs.
    ``data_path`` is only a fallback for lightweight callers that have no
    ``fig_path``.
    """
    fig_path = getattr(experiment, "fig_path", None)
    if fig_path:
        return fig_path
    data_path = getattr(experiment, "data_path", None)
    if data_path:
        return data_path
    return "."


def run_dirs(experiment, pipeline_name, run_label, if_exists, *, clear_overwrite=True):
    """Return ``(fig_dir, data_dir, resolved_label, reuse_existing)`` for one run.

    ``pipeline_name`` is the per-pipeline folder (e.g. ``"Correlation Pipeline"``).
    ``if_exists`` policy: ``'overwrite'`` clears the run folders when
    ``clear_overwrite`` is true, ``'version'`` picks the next free ``_vN`` so prior
    output is kept, ``'error'`` raises, ``'skip'`` returns ``reuse_existing=True``
    so the caller can return the cached manifest without recomputing.
    """
    root = data_root(experiment)
    base_fig = os.path.join(root, pipeline_name)
    base_data = base_fig
    policy = str(if_exists).strip().lower()
    if policy not in VALID_IF_EXISTS:
        raise ValueError(
            "if_exists must be 'overwrite', 'version', 'error', or 'skip'; "
            f"got {if_exists!r}.")

    legacy_base_data = getattr(experiment, "data_path", None)
    legacy_base = (
        os.path.join(legacy_base_data, pipeline_name)
        if legacy_base_data and os.path.abspath(legacy_base_data) != os.path.abspath(root)
        else None
    )

    def _dirs(lbl):
        safe = strip_name(str(lbl))
        if not safe:
            raise ValueError("run_label must resolve to a non-empty folder name.")
        return os.path.join(base_fig, safe), os.path.join(base_data, safe)

    def _legacy_dir(lbl):
        if legacy_base is None:
            return None
        safe = strip_name(str(lbl))
        return os.path.join(legacy_base, safe) if safe else None

    fig_dir, data_dir = _dirs(run_label)
    legacy_dir = _legacy_dir(run_label)
    exists = isdir(fig_dir) or isdir(data_dir)
    legacy_exists = legacy_dir is not None and isdir(legacy_dir)
    if not exists and not (policy == "overwrite" and legacy_exists):
        return fig_dir, data_dir, run_label, False
    if policy == "overwrite":
        if clear_overwrite:
            clear_run_dir(fig_dir, base_fig)
            clear_run_dir(data_dir, base_data)
            if legacy_dir is not None:
                clear_run_dir(legacy_dir, legacy_base)
        return fig_dir, data_dir, run_label, False
    if policy == "skip":
        return fig_dir, data_dir, run_label, True
    if policy == "error":
        raise RuntimeError(
            f"{pipeline_name} run {run_label!r} already exists. Pass "
            f"if_exists='overwrite'/'version'/'skip' or a different run_label.")
    n = 2
    while True:
        cand = f"{run_label}_v{n}"
        fig_dir, data_dir = _dirs(cand)
        if not (isdir(fig_dir) or isdir(data_dir)):
            return fig_dir, data_dir, cand, False
        n += 1


def _canon(value):
    """Order-stable, JSON-serialisable form of a slug payload value.

    Sorts dict keys and set members so equivalent configs (e.g. a
    ``reference_levels`` dict or a ``categorical`` set in different orders) hash
    identically. Lists keep their order (it may be meaningful). Leaf scalars are
    returned as-is; anything else falls back to ``str`` at ``json.dumps`` time.
    """
    if isinstance(value, dict):
        return {str(k): _canon(value[k]) for k in sorted(value, key=str)}
    if isinstance(value, (set, frozenset)):
        return sorted((_canon(v) for v in value), key=str)
    if isinstance(value, (list, tuple)):
        return [_canon(v) for v in value]
    return value


def slug(prefix, payload):
    """Deterministic ``"<prefix>_<6-hex>"`` run name from a JSON-stable payload.

    Identical settings hash to the same folder (so a repeat run reuses it); a
    different configuration hashes elsewhere and never collides. The payload is
    canonicalised first so dict/set ordering never changes the hash.
    """
    digest = hashlib.sha1(
        json.dumps(_canon(payload), sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:6]
    return f"{prefix}_{digest}"


def append_runs_index(experiment, pipeline_name, row, *, key="run_label"):
    """Append/replace one summary row in ``<pipeline>/_runs_index.csv`` (by ``key``)."""
    base_data = os.path.join(data_root(experiment), pipeline_name)
    makedirs(base_data)
    index_path = os.path.join(base_data, "_runs_index.csv")
    try:
        if isfile(index_path):
            existing = pd.read_csv(windows_extended_path(index_path))
            if key in existing.columns:
                existing = existing[
                    existing[key].astype(str) != str(row.get(key))]
            out = pd.concat([existing, pd.DataFrame([row])], ignore_index=True)
        else:
            out = pd.DataFrame([row])
        to_csv(out, index_path, index=False)
    except Exception as exc:  # never let index bookkeeping break a run
        from PyFLASH._logging import logger as _log
        _log.warn(f"[{pipeline_name}] Could not update runs index: {exc}")
