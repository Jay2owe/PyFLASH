"""PyFLASH adapter layer for the UI.

Pure Python: this module must **never** import ``streamlit``. All Streamlit
usage lives in ``app.py`` and ``pages/``. Keeping this layer Streamlit-free
makes it unit-testable in an environment with no UI dependencies installed.

Every heavy operation here wraps an *existing* PyFLASH function — no analysis
logic is reimplemented (house rule 1).
"""

from PyFLASH.serialization import load_state, save_state

__all__ = ["open_pickle", "save_pickle", "package_info"]


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
