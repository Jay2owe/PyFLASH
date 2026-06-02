"""PyFLASH adapter layer for the UI.

Pure Python: this module must **never** import ``streamlit``. All Streamlit
usage lives in ``app.py`` and ``pages/``. Keeping this layer Streamlit-free
makes it unit-testable in an environment with no UI dependencies installed.

Every heavy operation here wraps an *existing* PyFLASH function — no analysis
logic is reimplemented (house rule 1).
"""

import os

from PyFLASH.config import Config, check_directory
from PyFLASH.export import format_summary_for_display
from PyFLASH.serialization import load_state, save_state
from PyFLASH.utils import get_columns

__all__ = [
    "open_pickle",
    "save_pickle",
    "package_info",
    "roi_bases",
    "summary_table",
    "batch_overview",
    "validate_experiment_folder",
    "discover_experiments",
    "REQUIRED_ANY",
    "LAYOUT_DIRS",
]


def open_pickle(path: str):
    """Load a saved ``Batch`` or ``Experiment`` from a ``.pkl`` file.

    Thin wrapper over :func:`PyFLASH.serialization.load_state`. Paths are
    normalized (the default) so stale absolute paths rebase across machines.
    """
    return load_state(path, verbose=False)


def save_pickle(obj, path: str | None = None):
    """Save a ``Batch`` or ``Experiment`` to disk via ``save_state``."""
    return save_state(obj, path, verbose=False)


def package_info() -> dict:
    """Return a small import smoke-test payload for the landing page.

    Confirms core PyFLASH imports cleanly and exposes its key entry points,
    without importing any heavy or UI-only dependency.
    """
    import PyFLASH

    return {
        "import_ok": True,
        "version": getattr(PyFLASH, "__version__", None),
        "has_create_batch": hasattr(PyFLASH, "create_batch"),
        "has_load_state": hasattr(PyFLASH, "load_state"),
    }


# ── Summary browsing (Stage 02) ────────────────────────────────────────────


def roi_bases(batch) -> list:
    """Return the available ROI-base keys for a loaded ``Batch``/``Experiment``.

    These are the keys of ``batch.summaries`` (e.g. ``"SCN"``, ``"OC"``). Falls
    back to ``["SCN"]`` when ``summaries`` is missing/empty so the Summary page
    always has at least the backward-compatible default to offer.
    """
    summaries = getattr(batch, "summaries", None) or {}
    return list(summaries) or ["SCN"]


def summary_table(batch, roi_base=None, display=True, column_strings=None,
                  exclude=None):
    """Return one summary table for display or download.

    Parameters
    ----------
    batch
        A loaded ``Batch``/``Experiment`` exposing ``summaries`` and/or the
        backward-compat ``summary`` property.
    roi_base : str, optional
        Which ROI base to show (key of ``batch.summaries``). When ``None`` or
        unknown, falls back to ``batch.summary`` (the SCN table).
    display : bool
        When ``True`` (default) return a copy with human-readable column labels
        via :func:`PyFLASH.export.format_summary_for_display`; otherwise return
        the raw table.
    column_strings : list of str, optional
        Keep only columns containing any of these substrings (always retaining
        the ``AnimalName`` and ``Condition`` identifier columns). Uses
        :func:`PyFLASH.utils.get_columns`.
    exclude : str or list of str, optional
        Substrings whose columns are dropped during filtering.
    """
    summaries = getattr(batch, "summaries", None) or {}
    df = summaries.get(roi_base) if roi_base else None
    if df is None:
        df = getattr(batch, "summary", None)

    if column_strings:
        # get_columns(df, column_strings=..., exclude='') — exclude must be a
        # str/list, never None (it is iterated over).
        matched = get_columns(df, column_strings=column_strings,
                              exclude=exclude or "")
        keep = ["AnimalName", "Condition"] + matched
        df = df[[c for c in keep if c in df.columns]]

    return format_summary_for_display(df) if display else df


def batch_overview(batch) -> dict:
    """Return the same facts ``load_state(verbose=True)`` reports, as a dict.

    Used by the Project page to show a loaded object's identity at a glance:
    name, summary shape, condition names, markers, and experiment names.
    """
    summary = getattr(batch, "summary", None)
    shape = tuple(summary.shape) if summary is not None else None
    return {
        "name": getattr(batch, "name", "?"),
        "type": type(batch).__name__,
        "summary_shape": shape,
        "roi_bases": roi_bases(batch),
        "conditions": [getattr(c, "name", str(c))
                       for c in getattr(batch, "condition_list", []) or []],
        "markers": sorted(str(m) for m in (getattr(batch, "markers", None) or [])),
        "experiments": [getattr(e, "name", str(e))
                        for e in getattr(batch, "experiment_list", []) or []],
    }


# ── Experiment folder validation (Stage 03) ─────────────────────────────────

# These mirror the discovery rule in ``factory.py`` (the ``isinstance(str)``
# branch of ``create_batch``) **read-only**: we never import or call core
# processing, just replicate the os.path checks so the UI can give pre-flight
# feedback before a long run (house rule 1). Keep these in sync with
# ``PyFLASH/factory.py`` lines 176-184.
REQUIRED_ANY = ["Objects", "Attributes", "ROI Intensities"]
LAYOUT_DIRS = ["Objects", "Cells", "ROI Intensities", "Attributes", "ROIs",
               "Images"]


def validate_experiment_folder(path: str) -> dict:
    """Check one experiment folder against ``create_batch``'s discovery rule.

    Replicates ``factory.py:176-184`` read-only: a folder is *valid* when it
    contains a ``Data Analysis/`` subdirectory which in turn contains any of
    ``Objects`` / ``Attributes`` / ``ROI Intensities`` **or** any ``.csv``
    file. Performs no writes and never imports core processing.

    Parameters
    ----------
    path : str
        The experiment subfolder (the parent of ``Data Analysis/``). Resolved
        across machines via :func:`PyFLASH.config.check_directory`.

    Returns
    -------
    dict
        ``{"path", "valid", "reason", "has_images", "layout"}`` where
        ``layout`` maps each of :data:`LAYOUT_DIRS` to whether that
        subdirectory of ``Data Analysis/`` exists.
    """
    resolved = check_directory(path) or path
    data = os.path.join(resolved, "Data Analysis")
    ok = os.path.isdir(data)
    contents = os.listdir(data) if ok else []
    has_structure = ok and (
        any(d in contents for d in REQUIRED_ANY)
        or any(f.endswith(".csv") for f in contents)
    )
    layout = {
        d: bool(ok and os.path.isdir(os.path.join(data, d)))
        for d in LAYOUT_DIRS
    }
    if has_structure:
        reason = "ok"
    elif not ok:
        reason = "missing 'Data Analysis/'"
    else:
        reason = "no Objects/Attributes/ROI Intensities or CSVs"
    return {
        "path": resolved,
        "valid": bool(has_structure),
        "reason": reason,
        "has_images": layout["Images"],
        "layout": layout,
    }


def discover_experiments(root: str) -> list:
    """Validate every immediate subfolder of *root* as an experiment.

    Mirrors the ``isinstance(experiments, str)`` branch of ``create_batch``
    (``factory.py:169-186``): iterate the sorted subfolders of the resolved
    root and validate each. Unlike core, **all** subfolders are returned (each
    tagged ``valid`` True/False) so the UI can show ✓/✗ for every candidate
    rather than silently dropping invalid ones.

    Returns
    -------
    list of dict
        One :func:`validate_experiment_folder` result per subdirectory, each
        with an added ``"name"`` key (the subfolder name), sorted by name.
    """
    resolved = check_directory(root) or root
    out = []
    for sub in sorted(os.listdir(resolved)):
        p = os.path.join(resolved, sub)
        if os.path.isdir(p):
            r = validate_experiment_folder(p)
            r["name"] = sub
            out.append(r)
    return out
