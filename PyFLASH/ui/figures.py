"""Figure embedding helpers for the UI.

PyFLASH ``plot_*`` functions save high-DPI SVG to disk under ``batch.fig_path``
(gated by ``Config.SAVE_MODE``) and, in almost every case, **close the figure
and return non-``Figure`` data** (verified at runtime — e.g. ``plot_mean_bars``
returns ``run(...)`` output and ``plt.close``\\ s its shared canvas before
returning; ``plot_locations`` only returns a ``Figure`` through a private,
opt-in ``_return_fig`` path). The robust default (per the overview's
figure-embedding decision) is therefore to run a plot with saving enabled and
then embed the saved file rather than assume a ``Figure`` is returned.

This module stays Streamlit-free where it matters: the file-resolution and
SVG→PNG conversion logic is plain Python and unit-testable. The only
Streamlit-touching helper (:func:`embed_figure`) imports ``streamlit`` lazily
inside the function so importing this module never pulls in the UI dependency.
"""

import os
import time
from functools import lru_cache

__all__ = [
    "locate_saved_figures",
    "svg_to_png_bytes",
    "embed_figure",
    "is_figure",
]

def is_figure(obj) -> bool:
    """Return True when *obj* is a matplotlib ``Figure``.

    A defensive duck-typed check that does **not** import matplotlib (so this
    module stays light): a ``Figure`` exposes ``savefig`` and ``get_axes``.
    Returns False for ``None`` and for the plot-data objects most ``plot_*``
    functions actually return.
    """
    return (
        obj is not None
        and hasattr(obj, "savefig")
        and hasattr(obj, "get_axes")
    )


def locate_saved_figures(fig_path, since=None, exts=None,
                         limit=None) -> list:
    """Find recently-saved figure files under *fig_path*, newest first.

    Walks *fig_path* recursively (``plot_*`` writes into per-plot/per-ROI
    subfolders via ``save_fig``'s ``subfolder=`` argument) and collects files
    whose extension is in *exts*. When *since* is given, only files modified at
    or after that timestamp are returned — capture ``time.time()`` immediately
    *before* running a plot and pass it here to embed only that run's output.

    Parameters
    ----------
    fig_path : str
        A batch/experiment ``fig_path`` directory (the figure root). A missing
        or non-directory path yields an empty list (no error).
    since : float, optional
        A POSIX timestamp (``time.time()``); only files with
        ``mtime >= since - 1`` are kept. The one-second slack absorbs
        filesystem mtime granularity. ``None`` returns everything.
    exts : tuple of str
        File extensions to include (lowercased, dot-prefixed). Defaults to
        The same direct carrier registry used by ``PyFLASH.utils.save_fig``.
    limit : int, optional
        Keep at most this many files (after newest-first sorting). ``None``
        returns all matches.

    Returns
    -------
    list of str
        Absolute (or as-passed) file paths, sorted by modification time
        descending (newest first).
    """
    if not fig_path or not os.path.isdir(fig_path):
        return []

    if exts is None:
        from PyFLASH.utils import _DIRECT_FIGURE_EXTENSIONS
        exts = tuple('.' + extension for extension in _DIRECT_FIGURE_EXTENSIONS)

    cutoff = (since - 1) if since is not None else None
    found = []
    for dirpath, _dirnames, filenames in os.walk(fig_path):
        for name in filenames:
            if os.path.splitext(name)[1].lower() not in exts:
                continue
            full = os.path.join(dirpath, name)
            try:
                mtime = os.path.getmtime(full)
            except OSError:  # pragma: no cover - file vanished mid-walk
                continue
            if cutoff is not None and mtime < cutoff:
                continue
            found.append((mtime, full))

    found.sort(key=lambda item: item[0], reverse=True)
    paths = [full for _mtime, full in found]
    return paths[:limit] if limit else paths


def svg_to_png_bytes(svg_path):
    """Convert an SVG file to PNG bytes, or ``None`` if no converter is present.

    ``st.image`` cannot render SVG, so PNG bytes are preferred for embedding.
    Conversion is attempted with ``cairosvg`` (an optional ``[ui]`` dependency);
    when it is not installed this returns ``None`` and the caller falls back to
    embedding the raw SVG markup. No hard dependency on a converter is
    introduced (house rule: keep core/UI light).

    Parameters
    ----------
    svg_path : str
        Path to a ``.svg`` file.

    Returns
    -------
    bytes or None
        PNG image bytes, or ``None`` when ``cairosvg`` is unavailable or the
        conversion fails.
    """
    try:
        with open(svg_path, 'rb') as handle:
            svg_data = handle.read()
    except OSError:
        return None
    return _svg_to_png_bytes_cached(svg_data)


@lru_cache(maxsize=12)
def _svg_to_png_bytes_cached(svg_data):
    """Reuse at most twelve previews; changed files always invalidate them."""
    try:
        import cairosvg  # type: ignore
    except Exception:
        return None
    try:
        return cairosvg.svg2png(bytestring=svg_data)
    except Exception:  # pragma: no cover - converter present but failed
        return None


def preview_page(paths, page=0, limit=12):
    """Bound rendering, preserving access to every item in a large result."""
    if limit < 1:
        raise ValueError('Preview page size must be positive.')
    pages = max(1, (len(paths)+limit-1)//limit)
    page = max(0, min(int(page), pages-1))
    return list(paths[page*limit:(page+1)*limit]), page, pages


def embed_figure(result, fig_path, since=None, caption=None, limit=12, paths=None, titles=None, default_columns=2):
    """Display a plot's output in Streamlit: returned ``Figure`` or saved files.

    The single rendering entry point for the Plots page. Strategy (matching the
    runtime finding that plots save-and-close rather than return a ``Figure``):

    1. If *result* is itself a ``Figure`` (rare — only some opt-in paths), show
       it directly with ``st.pyplot``.
    2. Otherwise locate saved files and display PNG or SVG through ``st.image``.
       SVG stays a vector image, with its audit metadata preserved in the
       downloadable original. A download button is offered per file.

    ``streamlit`` is imported lazily here so importing this module stays
    Streamlit-free (house rule 2). Returns the list of embedded file paths (empty
    when nothing was found) so the page can warn the user if a plot produced no
    output (e.g. ``Config.SAVE_MODE`` is False).

    Parameters
    ----------
    result
        The return value of a plot call (may be a ``Figure`` or plot data).
    fig_path : str
        The batch/experiment ``fig_path`` to search for saved figures.
    since : float, optional
        Timestamp captured just before the plot ran (see
        :func:`locate_saved_figures`).
    caption : str, optional
        A caption shown above the embedded figures.
    limit : int
        Maximum number of saved files to embed (newest first).

    Returns
    -------
    list of str
        Paths of the saved files that were embedded (empty if a ``Figure`` was
        shown directly or nothing was found).
    """
    import streamlit as st

    if caption:
        st.caption(caption)

    if is_figure(result):
        st.pyplot(result)
        return []

    paths = locate_saved_figures(fig_path, since=since) if paths is None else list(paths)
    if not paths:
        return []
    from PyFLASH.ui.controls import widget
    import hashlib
    identity = hashlib.sha256('\0'.join(map(str, paths)).encode()).hexdigest()[:16]
    columns = 1
    if len(paths) > 1:
        strip = st.columns([2, 1], gap='small')
        columns = widget(strip[1], 'selectbox', 'Columns', [1, 2, 3, 4], index=[1,2,3,4].index(default_columns),
                         key='ui_preview_columns_'+identity,
                         help='Same-sized panels; original image aspect ratios are preserved.')
    visible, page, pages = preview_page(paths, limit=limit)
    if pages > 1:
        key = 'ui_preview_page_'+identity
        page = widget(strip[0], 'selectbox', 'Result page', list(range(pages)), key=key,
                      format_func=lambda index:f'{index+1} of {pages}',
                      help='Browse every result without loading hundreds of images at once.')
        visible, page, pages = preview_page(paths, page, limit)

    def show(path):
        name = os.path.basename(path)
        ext = os.path.splitext(path)[1].lower()
        if ext in {".png", ".svg", ".jpg", ".jpeg", ".jpe", ".webp", ".avif", ".tif", ".tiff"}:
            # The supported Streamlit version renders local SVG as an image.
            # Its embedded audit record stays in the download and never becomes
            # visible HTML; no raster conversion is needed on the script thread.
            st.image(path, caption=(titles or {}).get(path, name), width="stretch")
        try:
            with open(path, "rb") as fh:
                widget(st, 'download_button',
                    f"Download {name}", data=fh.read(),
                    file_name=name, key=f"dl_{path}",
                )
        except OSError:  # pragma: no cover - defensive
            pass
    for start in range(0, len(visible), columns):
        row = visible[start:start+columns]
        if columns == 1:
            show(row[0])
        else:
            cells = st.columns(columns, gap='small')
            for cell, path in zip(cells, row):
                with cell:
                    show(path)
    return visible
