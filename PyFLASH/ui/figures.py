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

__all__ = [
    "locate_saved_figures",
    "svg_to_png_bytes",
    "embed_figure",
    "is_figure",
]

# Extensions ``plot_*`` / ``save_fig`` may write (SVG is the default; PNG/HTML
# appear for some plot types and image exports).
_FIGURE_EXTS = (".svg", ".png")


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


def locate_saved_figures(fig_path, since=None, exts=_FIGURE_EXTS,
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
        ``(".svg", ".png")``.
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
        import cairosvg  # type: ignore
    except Exception:
        return None
    try:
        return cairosvg.svg2png(url=svg_path)
    except Exception:  # pragma: no cover - converter present but failed
        return None


def embed_figure(result, fig_path, since=None, caption=None, limit=12):
    """Display a plot's output in Streamlit: returned ``Figure`` or saved files.

    The single rendering entry point for the Plots page. Strategy (matching the
    runtime finding that plots save-and-close rather than return a ``Figure``):

    1. If *result* is itself a ``Figure`` (rare — only some opt-in paths), show
       it directly with ``st.pyplot``.
    2. Otherwise locate the files saved under *fig_path* since *since* and embed
       each: PNG inline via ``st.image``; SVG converted to PNG when ``cairosvg``
       is available, else rendered as inline SVG markup. A download button is
       offered per file.

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

    paths = locate_saved_figures(fig_path, since=since, limit=limit)
    if not paths:
        return []

    for path in paths:
        name = os.path.basename(path)
        ext = os.path.splitext(path)[1].lower()
        if ext == ".png":
            st.image(path, caption=name, use_container_width=True)
        elif ext == ".svg":
            png = svg_to_png_bytes(path)
            if png is not None:
                st.image(png, caption=name, use_container_width=True)
            else:
                # st.image can't render SVG; inline the markup as HTML instead.
                try:
                    with open(path, encoding="utf-8") as fh:
                        st.markdown(
                            f"**{name}**<br>{fh.read()}",
                            unsafe_allow_html=True,
                        )
                except Exception:  # pragma: no cover - defensive
                    st.caption(f"Saved (could not inline-render): {name}")
        try:
            with open(path, "rb") as fh:
                st.download_button(
                    f"Download {name}", data=fh.read(),
                    file_name=name, key=f"dl_{path}",
                )
        except OSError:  # pragma: no cover - defensive
            pass

    return paths
