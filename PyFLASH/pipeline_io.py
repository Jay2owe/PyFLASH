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
    with open(windows_extended_path(path), "w", encoding="utf-8") as fh:
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
