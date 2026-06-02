"""PyFLASH adapter layer for the UI.

Pure Python: this module must **never** import ``streamlit``. All Streamlit
usage lives in ``app.py`` and ``pages/``. Keeping this layer Streamlit-free
makes it unit-testable in an environment with no UI dependencies installed.

Every heavy operation here wraps an *existing* PyFLASH function — no analysis
logic is reimplemented (house rule 1).
"""

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
