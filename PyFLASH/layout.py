"""Custom matplotlib layout engine for uniform, overlap-free PyFLASH figures.

PyFLASH figures are produced by many independent plotting functions, several of
which hand-tune their own margins. They are saved with ``bbox_inches='tight'``
so the *figure* grows to fit overflowing (often 60°-rotated) tick labels while
the data axes keep their — frequently fixed-aspect — size. matplotlib's built-in
constrained/tight layout engines are the wrong fit here: they hold the figure
size fixed and *shrink the axes* to make room, starving dense heatmaps into thin
strips.

``PyFlashLayout`` is a custom :class:`matplotlib.layout_engine.LayoutEngine`
that instead **preserves axes size** and resolves only the text-vs-text overlaps
PyFLASH actually hits, by nudging/scaling the movable text:

* **Over-long titles** — an axes title wider than its own axes spills sideways
  over a neighbouring colorbar caption or panel. The engine shrinks the title
  font just enough to fit the axes width (down to a floor). Originals are
  remembered, so repeated draws are idempotent.
* **Suptitle over panel titles** — a ``fig.suptitle`` overlapping the per-axes
  titles/tick labels beneath it. The engine lifts the suptitle to sit just above
  the topmost axes decoration. ``bbox_inches='tight'`` then grows the figure to
  include it, so nothing is clipped and no axes shrink.
* **Crowded tick labels** — when a Cartesian axes has more (or taller/wider) tick
  labels than fit between adjacent ticks, the engine shrinks that axis' tick font
  just enough to clear, down to a floor. A safety net for dense matrices; polar
  (radar) axes are skipped and handled where the plot is built.

Because these are pure post-draw artist adjustments (no layout-grid machinery),
the engine works when attached *after* the figure is built. It is applied at the
single figure-save choke point (:func:`PyFLASH.utils.save_fig`); no
creation-time hook or pyplot monkeypatching is required. ``execute`` is written
to be idempotent because ``savefig(bbox_inches='tight')`` draws twice.

Requires matplotlib >= 3.6 (the public ``LayoutEngine`` extension point).

Opt-out
-------
A figure whose function deliberately positions its own text can opt out via
``fig._pyflash_manual_layout = True`` (see :func:`mark_manual_layout`); the
engine then leaves it untouched.
"""

from __future__ import annotations

# Attribute stamped on a Figure to make PyFlashLayout leave it alone.
_MANUAL_LAYOUT_ATTR = "_pyflash_manual_layout"
# Attribute remembering a title's original fontsize (for idempotent shrinking).
_ORIG_FONTSIZE_ATTR = "_pyflash_orig_fontsize"

# House tuning.
_MIN_TITLE_FONTSIZE = 9.0   # never shrink an over-long title below this (pt)
_TITLE_FIT_FACTOR = 0.98    # target title width as a fraction of its axes width
_SUPTITLE_PAD_PX = 8.0      # gap left between a lifted suptitle and the decoration below


def _layout_engine_base():
    """Import the LayoutEngine ABC lazily (keeps ``import PyFLASH`` matplotlib-free)."""
    from matplotlib.layout_engine import LayoutEngine
    return LayoutEngine


def mark_manual_layout(fig, manual=True):
    """Flag (or un-flag) *fig* so :class:`PyFlashLayout` leaves it untouched.

    Call this from a plotting function that deliberately positions its own
    titles/suptitle and does not want the central engine to adjust them.
    """
    setattr(fig, _MANUAL_LAYOUT_ATTR, bool(manual))
    return fig


def is_manual_layout(fig):
    """True if *fig* opted out of central layout via :func:`mark_manual_layout`."""
    return bool(getattr(fig, _MANUAL_LAYOUT_ATTR, False))


def _renderer(fig):
    """Best-effort renderer for measuring text/axes extents inside ``execute``."""
    try:
        return fig._get_renderer()
    except Exception:
        try:
            return fig.canvas.get_renderer()
        except Exception:
            return None


def _fit_overlong_titles(fig, renderer, *, min_size=_MIN_TITLE_FONTSIZE,
                         factor=_TITLE_FIT_FACTOR):
    """Shrink any axes title wider than its axes so it can't spill into neighbours.

    Idempotent: each axes' original title fontsize is remembered and the title is
    reset to it before re-measuring, so running this on every draw converges.
    """
    for ax in fig.axes:
        title = ax.title
        if not title.get_text():
            continue
        orig = getattr(title, _ORIG_FONTSIZE_ATTR, None)
        if orig is None:
            orig = float(title.get_fontsize())
            setattr(title, _ORIG_FONTSIZE_ATTR, orig)
        # Always measure from the original size so the operation is idempotent.
        title.set_fontsize(orig)
        try:
            title_w = title.get_window_extent(renderer).width
            axes_w = ax.get_window_extent(renderer).width
        except Exception:
            continue
        if axes_w > 0 and title_w > axes_w * factor:
            scaled = orig * (axes_w * factor) / title_w
            title.set_fontsize(max(min_size, scaled))


_MIN_TICK_FONTSIZE = 6.0    # floor when shrinking crowded tick labels


def _fit_axis_ticklabels(ax, which, renderer, *, min_size=_MIN_TICK_FONTSIZE):
    """Shrink one axis' tick labels if they are tall/wide enough to overlap.

    Compares each label's extent along the axis to the spacing between adjacent
    ticks (both in display pixels) and scales the font down just enough to clear,
    down to ``min_size``. Idempotent (original size remembered, reset before
    measuring). Skips rotated x labels (rotation already prevents horizontal
    overlap; their vertical extent is absorbed by ``bbox_inches='tight'``).
    """
    axis = ax.yaxis if which == "y" else ax.xaxis
    labels = [t for t in axis.get_ticklabels() if t.get_text()]
    if len(labels) < 2:
        return
    if which == "x" and (float(labels[0].get_rotation()) % 180.0) != 0.0:
        return
    locs = list(axis.get_ticklocs())
    if len(locs) < 2:
        return
    attr = "_pyflash_orig_%stick_fs" % which
    orig = getattr(ax, attr, None)
    if orig is None:
        orig = float(labels[0].get_fontsize())
        setattr(ax, attr, orig)
    for lab in labels:
        lab.set_fontsize(orig)
    try:
        if which == "y":
            pts = ax.transData.transform([(0.0, y) for y in locs])
            coords = sorted(p[1] for p in pts)
            extents = [lab.get_window_extent(renderer).height for lab in labels]
        else:
            pts = ax.transData.transform([(x, 0.0) for x in locs])
            coords = sorted(p[0] for p in pts)
            extents = [lab.get_window_extent(renderer).width for lab in labels]
    except Exception:
        return
    spacing = min((b - a) for a, b in zip(coords, coords[1:]) if (b - a) > 0) \
        if len(coords) > 1 else 0.0
    if spacing <= 0:
        return
    max_ext = max(extents)
    # Only act on genuine overlap (label extent exceeds the inter-tick gap).
    if max_ext > spacing:
        scaled = max(min_size, orig * spacing / max_ext)
        if scaled < orig:
            for lab in labels:
                lab.set_fontsize(scaled)


def _fit_tick_labels(fig, renderer):
    """Shrink crowded tick labels on every Cartesian axes (polar handled at source)."""
    for ax in fig.axes:
        if getattr(ax, "name", "") == "polar":
            continue
        _fit_axis_ticklabels(ax, "y", renderer)
        _fit_axis_ticklabels(ax, "x", renderer)


def _lift_suptitle(fig, renderer, *, pad_px=_SUPTITLE_PAD_PX):
    """Move a suptitle to sit just above the topmost axes decoration (no axes shrink).

    Idempotent: the target is computed from the axes' tight bounding boxes, which
    don't depend on the suptitle's own position.
    """
    sup = getattr(fig, "_suptitle", None)
    if sup is None or not sup.get_text():
        return
    tops = []
    for ax in fig.axes:
        try:
            bb = ax.get_tightbbox(renderer)
        except Exception:
            bb = None
        if bb is not None:
            tops.append(bb.y1)
    if not tops:
        return
    fig_h = fig.bbox.height
    if fig_h <= 0:
        return
    target = (max(tops) + pad_px) / fig_h
    sup.set_verticalalignment("bottom")
    sup.set_y(target)


def _build_engine_class():
    """Construct the PyFlashLayout class against the live matplotlib ABC (cached)."""
    LayoutEngine = _layout_engine_base()

    class PyFlashLayout(LayoutEngine):
        """One uniform, overlap-free layout for every PyFLASH figure.

        Unlike constrained/tight layout it never repositions or shrinks the data
        axes; it only scales over-long titles and lifts an overlapping suptitle,
        leaning on ``bbox_inches='tight'`` to grow the figure around them.
        """

        # We never call subplots_adjust ourselves; allow callers to.
        _adjust_compatible = True
        _colorbar_gridspec = False

        def execute(self, fig):
            if is_manual_layout(fig):
                return None
            renderer = _renderer(fig)
            if renderer is None:
                return None
            try:
                _fit_overlong_titles(fig, renderer)
            except Exception:
                pass
            try:
                _fit_tick_labels(fig, renderer)
            except Exception:
                pass
            try:
                _lift_suptitle(fig, renderer)
            except Exception:
                pass
            return None

    return PyFlashLayout


_PYFLASH_LAYOUT_CLASS = None


def get_layout_class():
    """Return (and cache) the PyFlashLayout class bound to the live matplotlib."""
    global _PYFLASH_LAYOUT_CLASS
    if _PYFLASH_LAYOUT_CLASS is None:
        _PYFLASH_LAYOUT_CLASS = _build_engine_class()
    return _PYFLASH_LAYOUT_CLASS


def default_layout_engine():
    """A fresh :class:`PyFlashLayout` instance."""
    return get_layout_class()()


def apply_pyflash_layout(fig):
    """Attach :class:`PyFlashLayout` to *fig* unless it opted out or chose its own engine.

    Safe to call unconditionally at the save choke point: it is a no-op for
    figures flagged via :func:`mark_manual_layout`, never raises, and respects a
    figure that was deliberately created with another engine (e.g.
    ``layout="constrained"``) — only figures with no layout engine adopt
    PyFlashLayout, so existing constrained/tight figures are left as authored.
    """
    if is_manual_layout(fig):
        return fig
    try:
        existing = fig.get_layout_engine()
        if existing is not None and not isinstance(existing, get_layout_class()):
            # A real engine (constrained/tight/placeholder) was chosen on purpose.
            from matplotlib.layout_engine import PlaceHolderLayoutEngine
            if not isinstance(existing, PlaceHolderLayoutEngine):
                return fig
        fig.set_layout_engine(default_layout_engine())
    except Exception:
        pass
    return fig
