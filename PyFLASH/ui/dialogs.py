"""Native folder picker for the UI.

``tkinter`` is imported lazily and guarded so that importing this module on a
headless / minimal Python (no Tk) never crashes — it just returns ``None`` and
the caller falls back to a typed path field (relevant in Stage 03).

No Streamlit import here.
"""

__all__ = ["pick_directory"]


def pick_directory(initial=None):
    """Open a native "choose folder" dialog; return the path or ``None``.

    Returns ``None`` if tkinter is unavailable or the user cancels.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:
        return None

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        path = filedialog.askdirectory(initialdir=initial or ".")
    finally:
        root.destroy()
    return path or None
