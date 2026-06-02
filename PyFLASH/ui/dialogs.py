"""Native folder picker for the UI.

``tkinter`` is imported lazily and guarded so that importing this module on a
headless / minimal Python (no Tk) never crashes — it just returns ``None`` and
the caller falls back to a typed path field (relevant in Stage 03).

No Streamlit import here.
"""

__all__ = ["pick_directory", "pick_file"]


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


def pick_file(patterns=None, initial=None):
    """Open a native "choose file" dialog; return the path or ``None``.

    Parameters
    ----------
    patterns : list of (label, glob) tuples, optional
        File-type filters, e.g. ``[("Pickle", "*.pkl")]``. Defaults to all
        files when omitted.
    initial : str, optional
        Initial directory to open the dialog in.

    Returns ``None`` if tkinter is unavailable or the user cancels.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:
        return None

    filetypes = list(patterns) if patterns else [("All files", "*.*")]

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        path = filedialog.askopenfilename(
            initialdir=initial or ".",
            filetypes=filetypes,
        )
    finally:
        root.destroy()
    return path or None
