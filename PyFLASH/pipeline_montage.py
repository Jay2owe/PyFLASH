"""
Pipeline montage layer — one "overview montage" figure per pipeline run.

Each analysis pipeline (``correlation`` / ``adjusted_correlation`` /
``data_overview``) already saves many figures into its run folder. This module
adds a single extra figure: a contact-sheet **montage** of that run's *most
important* graphs (for example coefficient / gate matrices, raw-vs-adjusted
matrices, missingness / covariation maps, and regression plots when a pipeline
renders them), tiled into one PNG that sorts to the top of the folder. It is the
at-a-glance "what did this run find" panel an agent or a human can read without
opening a dozen files.

How it works (mirrors the describe layer in :mod:`PyFLASH.report`)
-----------------------------------------------------------------
The mechanism is an **opt-in, inert-by-default capture collector** plus a thin
observer on :func:`PyFLASH.utils.save_fig` (the single choke point every pipeline
uses to write a figure). Nothing changes on the plotting path unless a montage
session is armed:

  * :func:`montage_pipeline` is a decorator worn by every public pipeline. It
    arms a capture session around the call, then builds the montage from the
    captured panels and writes it into the run's ``fig_dir``.
  * While a session is armed, every ``save_fig`` call notifies :func:`_observer`
    with the *live* matplotlib figure (the caller closes it immediately after, so
    the panel must be rasterised here and now). Capture is **explicit**, so the
    montage stays curated rather than scooping up every auxiliary heatmap:
      - figures flagged ``save_fig(..., montage=True)`` are the "headline" panels
        and are always captured;
      - other figures are captured only inside a :func:`capture_secondary` block
        — the pipeline wraps its regression loop in one so the strongest
        regression scatter plots ride along, while p/q-value and difference
        matrices (saved without the flag, outside the block) stay off the montage.
        Pipelines that do not render regression figures simply contribute their
        headline panels.
  * :func:`build_montage` tiles the captured PNG panels into one grid figure
    (headline panels first, then the captured secondaries).

Uniformity is *enforced, not hoped for*: ``tests/test_pipeline_montage.py`` fails
until every name in ``pipeline.__all__`` is either decorated with
:func:`montage_pipeline` or listed in ``pipeline.MONTAGE_EXEMPT`` with intent. So
a newly-added pipeline function cannot silently ship without an overview montage
(or a conscious decision that it produces no figures to montage).

Like :mod:`PyFLASH.report`, this module is deliberately dependency-light at import
time — matplotlib / numpy are imported lazily inside the functions that need them,
so ``import PyFLASH.pipeline_montage`` stays cheap.
"""

from __future__ import annotations

import functools
import inspect
import io
import math
import os
from contextlib import contextmanager

from PyFLASH._logging import logger as _log

# Default filename — the leading "!" sorts the montage to the top of the folder
# (Windows Explorer's StrCmpLogicalW orders punctuation above 0-9 and A-Z) so it
# is the first thing seen when browsing a run's figures, without leaking sort
# scaffolding like the old "00 - " prefix into a user-facing name. Overridable
# per-run via ``Config.MONTAGE_FILENAME`` (resolved by ``_montage_filename``).
DEFAULT_MONTAGE_FILENAME = "! Overview Montage"
# Historical montage names, tried as a fallback when locating a montage a prior
# run already wrote (so reused runs made before the rename still resolve).
LEGACY_MONTAGE_FILENAMES = ("00 - Overview Montage",)


def _montage_filename(explicit=None):
    """Resolve the montage filename (no extension) for a run.

    An ``explicit`` value (passed to the decorator) always wins; otherwise read
    ``Config.MONTAGE_FILENAME`` so a user can override or restore the old name
    without a code edit, falling back to :data:`DEFAULT_MONTAGE_FILENAME`. Fully
    guarded — a heavy or circular ``Config`` import must never raise into a run.
    """
    if explicit is not None:
        return explicit
    try:
        from PyFLASH.config import Config
        return getattr(Config, "MONTAGE_FILENAME", None) or DEFAULT_MONTAGE_FILENAME
    except Exception:
        return DEFAULT_MONTAGE_FILENAME
# DPI for the per-panel raster snapshots. Panels are small tiles, so a modest DPI
# keeps the captured bytes (and the final montage) light without looking blurry.
CAPTURE_DPI = 96
# Cap how many *secondary* figures (e.g. regression scatter plots, captured only
# inside a capture_secondary block) we rasterise per run, so a run that draws
# dozens of regressions can't balloon capture cost. Key (montage=True) figures are
# always captured.
MAX_NONKEY_CAPTURE = 12
# Default number of tiles shown in the montage grid (headline panels first, then
# regressions). Anything beyond is summarised in an overflow caption.
DEFAULT_MAX_PANELS = 16


# ── capture-session state (single-process, single-threaded; see report.py) ───
def _fresh_state():
    return {"active": False, "panels": [], "n_nonkey_captured": 0,
            "n_nonkey_omitted": 0, "capture_secondary": False,
            "secondary_label": None}


_STATE = _fresh_state()


def is_active() -> bool:
    """True when a montage capture session is armed (``save_fig`` checks nothing —
    the observer does — but tests and callers can introspect)."""
    return bool(_STATE["active"])


def _rasterize(figure, dpi: int = CAPTURE_DPI):
    """Snapshot a live matplotlib figure to PNG bytes on a white background.

    Pipeline figures are saved transparent as SVG; for a montage tile we want an
    opaque white panel. Fully guarded — capture must never raise into ``save_fig``.
    """
    try:
        buf = io.BytesIO()
        figure.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                       facecolor="white", edgecolor="none")
        buf.seek(0)
        return buf.getvalue()
    except Exception:
        return None


def _observer(figure, full_path, image_name, subfolder, key) -> None:
    """``save_fig`` observer: capture a panel while a session is armed.

    Registered with :func:`PyFLASH.utils.register_fig_save_observer` for the life
    of a capture session. Guarded so a capture failure can never break a figure
    save. A figure is captured only when it is a headline figure (``key=True``,
    i.e. ``save_fig(..., montage=True)``) or when a :func:`capture_secondary`
    block is active; secondary captures are rasterised up to
    :data:`MAX_NONKEY_CAPTURE`, after which they are merely counted as omitted.
    Everything else (auxiliary p/q-value or difference matrices) is ignored.
    """
    if not _STATE["active"]:
        return
    try:
        is_key = bool(key)
        secondary = (not is_key) and bool(_STATE.get("capture_secondary"))
        if not is_key and not secondary:
            return  # auxiliary figure, not requested for the montage
        if secondary and _STATE["n_nonkey_captured"] >= MAX_NONKEY_CAPTURE:
            _STATE["n_nonkey_omitted"] += 1
            return
        png = _rasterize(figure)
        if png is None:
            return
        if secondary:
            _STATE["n_nonkey_captured"] += 1
        _STATE["panels"].append({
            "name": str(image_name),
            "subfolder": (str(subfolder) if subfolder else None),
            "path": (str(full_path) if full_path else None),
            "key": is_key,
            "category": (None if is_key else _STATE.get("secondary_label")),
            "png": png,
        })
    except Exception:
        return


@contextmanager
def capture_secondary(label="secondary"):
    """Within this block, capture *non-headline* figures onto the montage too.

    Used by a pipeline to wrap the section that draws its supporting figures (e.g.
    the regression scatter plots) so they ride along on the overview montage as
    secondary panels, while figures saved outside the block without
    ``montage=True`` (p/q-value matrices, difference matrices) stay off it.
    Nesting-safe and a true no-op when no capture session is armed (a pipeline run
    with ``montage=False`` / ``save=False`` still enters this block, and must not
    touch the inert global state).
    """
    if not _STATE["active"]:
        yield
        return
    prev = _STATE.get("capture_secondary", False)
    prev_label = _STATE.get("secondary_label")
    _STATE["capture_secondary"] = True
    _STATE["secondary_label"] = str(label)
    try:
        yield
    finally:
        _STATE["capture_secondary"] = prev
        _STATE["secondary_label"] = prev_label


@contextmanager
def capture_session():
    """Arm a montage capture session, registering the ``save_fig`` observer.

    Nesting-safe: a child run may re-enter a decorated pipeline while a parent
    session is notionally active. Each session snapshots and restores the prior
    state, and the observer is only unregistered when the outermost session exits.
    (The specificity-queue path runs its per-condition children with
    ``montage=False`` so they don't open their own session — their figures are
    captured by the parent session for one combined montage.)
    """
    from PyFLASH import utils

    prev = dict(_STATE)
    _STATE.clear()
    _STATE.update(_fresh_state())
    _STATE["active"] = True
    utils.register_fig_save_observer(_observer)  # idempotent
    try:
        yield _STATE
    finally:
        was_nested = bool(prev.get("active"))
        _STATE.clear()
        _STATE.update(prev)
        if not was_nested:
            utils.unregister_fig_save_observer(_observer)


# ── montage rendering ────────────────────────────────────────────────────────
def _panel_caption(name, subfolder):
    """Short tile caption: ``group — name`` when a group subfolder disambiguates."""
    parts = [p for p in str(subfolder or "").replace("\\", "/").split("/")
             if p and p != "Matrices"]
    grp = parts[0] if parts else None
    return f"{grp} — {name}" if grp else str(name)


def _grid_shape(n):
    """Pick a near-square grid, capped at 4 columns for readability."""
    if n <= 0:
        return 0, 0
    ncols = min(4, max(1, int(round(math.sqrt(n)))))
    nrows = int(math.ceil(n / ncols))
    return nrows, ncols


def build_montage(panels, fig_dir, *, title, filename=None,
                  max_panels=DEFAULT_MAX_PANELS, n_nonkey_omitted=0):
    """Tile captured panels into one montage PNG in ``fig_dir``; return its path.

    Headline (``key=True``) panels come first in capture order, then the captured
    non-key panels (regressions). The grid is capped at ``max_panels`` tiles; any
    panels beyond that — plus non-key figures never captured (``n_nonkey_omitted``)
    — are summarised in an overflow caption. Returns ``None`` when there is nothing
    to montage. ``filename`` defaults to :func:`_montage_filename` (the config
    value, else :data:`DEFAULT_MONTAGE_FILENAME`); pass a string to force one.
    """
    filename = _montage_filename(filename)
    panels = [p for p in (panels or []) if p and p.get("png")]
    if not panels or not fig_dir:
        return None

    from matplotlib import pyplot as plt
    from PyFLASH import pipeline_io as _pio

    key_panels = [p for p in panels if p.get("key")]
    nonkey_panels = [p for p in panels if not p.get("key")]
    ordered = key_panels + nonkey_panels
    shown = ordered[:max_panels]
    omitted = (len(ordered) - len(shown)) + int(n_nonkey_omitted or 0)

    nrows, ncols = _grid_shape(len(shown))
    if nrows == 0:
        return None

    fig, axes = plt.subplots(nrows, ncols, figsize=(ncols * 4.2, nrows * 4.2),
                             squeeze=False)
    flat = axes.ravel()
    drawn = 0
    for ax, panel in zip(flat, shown):
        try:
            img = plt.imread(io.BytesIO(panel["png"]), format="png")
        except Exception:
            ax.axis("off")
            continue
        ax.imshow(img)
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.set_title(_panel_caption(panel.get("name"), panel.get("subfolder")),
                     fontsize=8)
        drawn += 1
    for ax in flat[len(shown):]:
        ax.axis("off")
    if drawn == 0:
        plt.close(fig)
        return None

    fig.suptitle(title, fontsize=14, fontweight="bold")
    if omitted > 0:
        fig.text(0.5, 0.005,
                 f"… {omitted} further figure(s) not shown — "
                 "see the run folder for the full set.",
                 ha="center", va="bottom", fontsize=8, style="italic")
    fig.tight_layout(rect=(0, 0.02, 1, 0.96))

    out_path = os.path.join(fig_dir, f"{filename}.png")
    _pio.makedirs(fig_dir)
    try:
        fig.savefig(_pio.windows_extended_path(out_path), format="png",
                    dpi=150, facecolor="white")
    finally:
        plt.close(fig)
    return out_path


# ── decorator (the enforced format for every pipeline) ───────────────────────
def _should_montage(result):
    """A normal single run that wrote figures — not a queue parent or a reused run."""
    if not isinstance(result, dict):
        return False
    if result.get("queued") or result.get("reused"):
        return False
    return bool(result.get("fig_dir"))


def _run_title(base, result):
    label = result.get("run_label") if isinstance(result, dict) else None
    return f"{base} — {label}" if label else str(base)


def _existing_montage(result, filename):
    """Path to a montage a *reused* run already wrote, if it is still on disk.

    A reused run (``if_exists='skip'``) returns its cached manifest without
    recomputing, so no montage is built — but the original run's montage usually
    still exists. Point the returned dict at it so ``result["montage"]`` is
    consistent whether or not the run was reused. Returns ``None`` when the run
    wasn't reused, has no ``fig_dir``, or no montage file is present.
    """
    if not isinstance(result, dict) or not result.get("reused"):
        return None
    fig_dir = result.get("fig_dir")
    if not fig_dir:
        return None
    from PyFLASH import pipeline_io as _pio

    # Try the current name first, then any historical name, so a run reused after
    # the montage rename still resolves the montage the original run wrote.
    for name in (filename, *LEGACY_MONTAGE_FILENAMES):
        candidate = os.path.join(fig_dir, f"{name}.png")
        if _pio.isfile(candidate):
            return candidate
    return None


def montage_pipeline(*, title=None, filename=None,
                     max_panels=DEFAULT_MAX_PANELS):
    """Decorate a pipeline so every run emits an overview montage of its key graphs.

    This is the **enforced format** for the pipeline module. A wrapped pipeline:

    * is captured while it runs (the ``save_fig`` observer collects panels), and
    * after returning, gets a montage written into ``result["fig_dir"]`` and its
      path recorded under ``result["montage"]``.

    The montage is built only when both ``save`` and ``montage`` are truthy for the
    call (resolved from the bound signature, so it works whether they were passed
    positionally or by keyword). A specificity *queue* is one merged run sharing a
    single folder, so it builds one combined montage spanning every condition (the
    per-condition children run with ``montage=False`` and are captured by this
    parent session — see ``_pipeline_specificity_queue``). A reused run
    (``if_exists='skip'``) doesn't rebuild, but ``result["montage"]`` is pointed at
    the montage the original run already wrote when it is still on disk, so the
    returned key is consistent regardless of reuse. Montage building is
    best-effort: a failure is logged, never raised, so it can never break an
    otherwise-successful analysis.

    Adding a new pipeline? Give it a ``montage=True`` parameter, wear this
    decorator, and tag its headline ``save_fig`` calls with ``montage=True`` (see
    the contract in ``PyFLASH/pipeline.py`` and ``tests/test_pipeline_montage.py``).
    """
    def decorator(func):
        base_title = title or func.__name__.replace("_", " ").title()
        sig = inspect.signature(func)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                bound = sig.bind_partial(*args, **kwargs)
                bound.apply_defaults()
                save_on = bool(bound.arguments.get("save", True))
                montage_on = bool(bound.arguments.get("montage", True))
            except TypeError:
                save_on = montage_on = True
            try:
                from PyFLASH.config import Config
                save_on = save_on and bool(Config.SAVE_MODE)
            except Exception:
                pass

            if not (save_on and montage_on):
                return func(*args, **kwargs)

            # Resolve once per run so build + reuse-lookup agree on the name and a
            # user's Config.MONTAGE_FILENAME override is picked up at call time.
            resolved_filename = _montage_filename(filename)
            with capture_session() as state:
                result = func(*args, **kwargs)
                if _should_montage(result):
                    try:
                        path = build_montage(
                            list(state["panels"]),
                            result.get("fig_dir"),
                            title=_run_title(base_title, result),
                            filename=resolved_filename,
                            max_panels=max_panels,
                            n_nonkey_omitted=state.get("n_nonkey_omitted", 0),
                        )
                        if path:
                            result["montage"] = path
                    except Exception as exc:  # never break a successful run
                        _log.warn(f"[montage] {base_title}: montage build failed: {exc}")
                else:
                    # A reused run (if_exists='skip') doesn't rebuild — point it at
                    # the montage the original run already wrote, if it survives.
                    existing = _existing_montage(result, resolved_filename)
                    if existing:
                        result["montage"] = existing
            return result

        wrapper.__montage_pipeline__ = True
        return wrapper

    return decorator
