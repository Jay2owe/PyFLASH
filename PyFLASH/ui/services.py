"""PyFLASH adapter layer for the UI.

Pure Python: this module must **never** import ``streamlit``. All Streamlit
usage lives in ``app.py`` and ``pages/``. Keeping this layer Streamlit-free
makes it unit-testable in an environment with no UI dependencies installed.

Every heavy operation here wraps an *existing* PyFLASH function — no analysis
logic is reimplemented (house rule 1).
"""

import contextlib
import inspect
import io
import os
import re

from PyFLASH._logging import logger
from PyFLASH.conditions import _resolve_color
from PyFLASH.config import Config, check_directory
from PyFLASH.export import format_summary_for_display
from PyFLASH.factory import create_batch
from PyFLASH.serialization import load_state, save_state
from PyFLASH.ui.project_io import build_condition_list
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
    "build_conditions",
    "preview_conditions",
    "resolve_color",
    "capture_output",
    "run_create_batch",
    "validate_regex",
    "export_excel",
    "save_batch",
    "available_plots",
    "run_plot_spec",
    "run_quick_plot",
    "IMAGE_PLOT_TYPES",
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


# ── Conditions builder (Stage 04) ───────────────────────────────────────────


def resolve_color(color, index=0) -> str:
    """Resolve a color spec to a hex string for swatch preview.

    Thin wrapper over :func:`PyFLASH.conditions._resolve_color`: a
    ``Config.COLORS`` key (wins), a CSS/matplotlib name, a ``#hex`` (passed
    through), or ``None`` to auto-assign from the Okabe-Ito palette by *index*.
    Lets the page show users the *actual* hex before they build, so a palette
    key shadowing a CSS name is not a surprise (Stage 04 known risk).
    """
    return _resolve_color(color, index)


def build_conditions(spec):
    """Rebuild a ``conditionList`` from a JSON-serializable conditions *spec*.

    Thin wrapper over :func:`PyFLASH.ui.project_io.build_condition_list` so the
    page has a single ``services`` entry point. Replays the spec through
    :class:`PyFLASH.conditions.ConditionBuilder` — it never unpickles built
    condition objects. Builder ``ValueError``\\ s (including difflib "Did you
    mean…?" suggestions for bad comparison names) propagate to the caller so the
    page can surface them inline.
    """
    return build_condition_list(spec)


def preview_conditions(cl) -> dict:
    """Summarize a built ``conditionList`` for display (names, colors, pairs).

    Returns a plain dict so the page can render swatches, the resolved ``'1-2'``
    comparison index strings, and the per-condition explanation expansion
    without touching core objects.

    Returns
    -------
    dict
        ``{"factor", "conditions": [{"name","label","color","factor",
        "explanation"}], "comparisons": [...], "labelled_comparisons": [...]}``.
        ``comparisons`` are the resolved ``'1-2'`` index strings exactly as the
        builder produced them; ``labelled_comparisons`` map those back to
        ``"<short> vs <short>"`` for human-readable preview.
    """
    if cl is None:
        return {"factor": None, "conditions": [], "comparisons": None,
                "labelled_comparisons": []}

    conditions = [
        {
            "name": getattr(c, "name", None),
            "label": getattr(c, "label", None),
            "color": getattr(c, "color", None),
            "factor": getattr(c, "factor", None),
            "explanation": getattr(c, "factor_explanation", None),
        }
        for c in cl.condition_list
    ]

    comparisons = cl.comparisons
    labelled = []
    if comparisons:
        # 1-based index -> short name, for a human-readable echo of '1-2'.
        names = [c["name"] for c in conditions]
        for pair in comparisons:
            try:
                a, b = (int(x) for x in str(pair).split("-"))
                labelled.append(f"{names[a - 1]} vs {names[b - 1]}")
            except (ValueError, IndexError):
                labelled.append(str(pair))

    return {
        "factor": cl.factor,
        "conditions": conditions,
        "comparisons": comparisons,
        "labelled_comparisons": labelled,
    }


# ── Batch processing (Stage 05) ─────────────────────────────────────────────


@contextlib.contextmanager
def capture_output():
    """Capture all PyFLASH output emitted inside the ``with`` block.

    Off-notebook, PyFLASH writes through two channels: the package
    :data:`PyFLASH._logging.logger` (status/timing/confirm lines) and plain
    ``stdout`` (``ProgressTracker`` falls back to ``print`` when ``IPython``
    display is unavailable — ``utils.py:452``). Both are redirected into a
    single in-memory buffer so the page can show one readable log.

    ``logger.set_output`` is **process-global**, so the previous output target
    is always restored in ``finally`` — even if the wrapped call raises (house
    rule: never leak the redirect). We avoid ``logger.set_output(None)`` on
    restore because that hard-resets to ``sys.stdout`` rather than whatever was
    in place before; we re-assign the captured previous target directly.

    Yields
    ------
    io.StringIO
        The buffer accumulating both logger and stdout text. Read it with
        ``buf.getvalue()`` after (or during) the block.
    """
    buf = io.StringIO()
    prev = logger._output
    logger.set_output(buf)
    try:
        # ProgressTracker prints to stdout when not in a notebook; redirect it
        # into the same buffer as the logger so the captured log is complete.
        with contextlib.redirect_stdout(buf):
            yield buf
    finally:
        # Restore the exact prior target (not sys.stdout) — set_output(obj)
        # assigns it verbatim, so this round-trips _output cleanly.
        logger._output = prev


def run_create_batch(*, name, conditions, batch_path, experiments=None,
                     pickle_path=None, threshold=None, rerun=False,
                     import_images=True, reimport_images=False):
    """Run :func:`PyFLASH.factory.create_batch`, capturing its progress log.

    Thin wrapper that forwards every argument to ``create_batch`` (with
    ``progress=True``) inside :func:`capture_output`, so the long-running build
    streams its ``ProgressTracker`` steps and logger lines into a buffer instead
    of the terminal. No analysis logic is added here (house rule 1).

    ``create_batch`` is imported at module top as
    ``from PyFLASH.factory import create_batch`` specifically so tests can
    monkeypatch ``PyFLASH.ui.services.create_batch``.

    Parameters mirror ``create_batch``'s keyword-only surface: ``name``,
    ``conditions`` (a built ``conditionList``), ``batch_path``, optional
    ``experiments`` (dict/list/str/None for auto-discovery), ``pickle_path``
    (cache dir), ``threshold``, ``rerun``, ``import_images``, and
    ``reimport_images``.

    Returns
    -------
    tuple
        ``(batch, log_text)`` — the built/cached ``Batch`` and the full captured
        log string. On a cache hit the log still contains the
        ``ProgressTracker`` "Loaded existing pickle" line.

    Raises
    ------
    ValueError
        Propagated from ``create_batch`` (e.g. "No experiment folders found");
        the page catches and displays it cleanly. The output buffer is always
        restored first because :func:`capture_output` restores in ``finally``.
    """
    with capture_output() as buf:
        batch = create_batch(
            name,
            conditions,
            batch_path,
            experiments=experiments,
            threshold=threshold,
            pickle_path=pickle_path,
            rerun=rerun,
            import_images=import_images,
            reimport_images=reimport_images,
            progress=True,
        )
    return batch, buf.getvalue()


# ── Excel export & save-state (Stage 06) ────────────────────────────────────


def validate_regex(patterns):
    """Pre-compile a list of regex *patterns*, raising on the first bad one.

    Mirrors the validation ``batch.py:_prepare_export_regex_filters`` performs
    (it compiles each include/exclude pattern and re-raises as ``ValueError``),
    so the page can surface a friendly message *before* kicking off a slow
    export rather than failing mid-write. Empty/blank patterns and ``None`` are
    skipped — they impose no filter, matching how the core normalizer drops
    them.

    Parameters
    ----------
    patterns : iterable of str or None
        The candidate regex strings (typically one page field split on commas).

    Raises
    ------
    re.error
        From :func:`re.compile` on the first malformed pattern (e.g. ``"["``).
        The page catches this and shows the offending message.
    """
    for p in patterns or []:
        if p:
            re.compile(p)


def export_excel(batch, *, save_path=None, if_summary=True, if_extended=True,
                 behaviour=True, if_summary_exclude=None,
                 if_extended_exclude=None, behaviour_exclude=None,
                 if_summary_include=None, if_extended_include=None,
                 behaviour_include=None, capture=True):
    """Export the formatted Excel workbooks, capturing the progress log.

    Thin wrapper over :meth:`PyFLASH.batch.Batch.export_all_excel` (which
    delegates to ``export_excel``). Every toggle and include/exclude regex is
    forwarded verbatim; no filtering or analysis logic is reimplemented here
    (house rule 1). When *capture* is ``True`` the call runs inside
    :func:`capture_output`, so the per-sheet status lines and the
    ``"Exported … to …"`` confirmations stream into a buffer the page renders
    (the extended export can be slow — known risk in Stage 06).

    ``batch.export_all_excel`` itself re-raises a ``ValueError`` for malformed
    regex (``batch.py:50-57``) and writes a ``<stem>_RegexFilters.txt`` report
    beside each workbook; a batch with no behaviour table simply skips the
    behaviour workbook (``batch.py:961-964``). A relative ``save_path`` lands
    under the batch ``Exports/`` folder; an absolute one is used as-is
    (``batch.py:208-220``).

    Parameters
    ----------
    batch
        A loaded ``Batch`` exposing ``export_all_excel``.
    save_path : str, optional
        Target directory. ``None`` -> the batch ``Exports/`` folder.
    if_summary, if_extended, behaviour : bool
        Which workbooks to write.
    *_include, *_exclude : str or list of str, optional
        Per-workbook column-name regex filters (case-insensitive in core).
    capture : bool
        When ``True`` (default) run inside :func:`capture_output` and return the
        captured log; otherwise run directly and return ``""``.

    Returns
    -------
    str
        The captured log text (empty string when ``capture=False``).

    Raises
    ------
    ValueError
        Propagated from core for a malformed include/exclude regex; the page
        catches it and shows a clean message. The output buffer is always
        restored because :func:`capture_output` restores in ``finally``.
    """
    def _run():
        batch.export_all_excel(
            save_path=save_path,
            if_summary=if_summary,
            if_extended=if_extended,
            behaviour=behaviour,
            if_summary_exclude=if_summary_exclude,
            if_extended_exclude=if_extended_exclude,
            behaviour_exclude=behaviour_exclude,
            if_summary_include=if_summary_include,
            if_extended_include=if_extended_include,
            behaviour_include=behaviour_include,
        )

    if capture:
        with capture_output() as buf:
            _run()
        return buf.getvalue()
    _run()
    return ""


def save_batch(batch, filename):
    """Save the in-memory ``Batch`` to *filename*, returning the path written.

    Thin wrapper over :func:`PyFLASH.serialization.save_state` (imported at
    module top for ``open_pickle`` — reused here) with ``verbose=False`` so no
    output leaks to the terminal. ``save_state`` records ``_state_path`` on the
    object and creates the parent directory, so the page can show the path and
    re-open it via :func:`open_pickle` (Stage 02).

    Parameters
    ----------
    batch
        A ``Batch``/``Experiment`` to pickle.
    filename : str
        Destination ``.pkl`` path.

    Returns
    -------
    str
        The *filename* that was written (echoed back for the page to display).
    """
    save_state(batch, filename, verbose=False)
    return filename


# ── Plotting presets (Stage 07) ─────────────────────────────────────────────

# Plot types that require imported images / object locations to be present.
# These are deferred to Stage 08 (image / representative / location tools); the
# Quick-plot form routes them there rather than offering a parameter form.
IMAGE_PLOT_TYPES = ("locations", "images", "representative_images")


def available_plots() -> list:
    """Return the sorted plot-type names from ``spec.PLOT_REGISTRY``.

    These are the short keys (e.g. ``"mean_bars"``, ``"matrices"``) the Quick-plot
    tab and the Spec-file ``type`` field use. Resolving the registry does **not**
    import the heavy plotting module — ``PLOT_REGISTRY`` holds lazy string
    references that :func:`PyFLASH.spec._resolve_func` only resolves on demand
    (so importing ``services`` stays plotting-free, house rule 2).
    """
    from PyFLASH.spec import PLOT_REGISTRY

    return sorted(PLOT_REGISTRY)


def _build_plot_kwargs(func, params: dict) -> dict:
    """Filter *params* down to a kwargs dict valid for plot *func*.

    Mirrors the kwarg handling in :func:`PyFLASH.spec.run_spec` so a guided form
    behaves exactly like a declarative spec entry. Extracted as a standalone,
    side-effect-free helper so it can be unit-tested against a real plot
    function's signature **without** calling the plot (no data required).

    The three rules, in order:

    * ``"columns"`` is remapped to ``"filtered_columns"`` when the function takes
      ``filtered_columns`` (the notebook/spec name) but not ``columns``.
    * ``"specificity"`` values are converted from JSON/YAML lists to the tuple /
      list-of-tuples form the plot functions expect, via
      :func:`PyFLASH.spec._convert_specificity`.
    * any key not present in the function signature is dropped (unknown keys are
      silently ignored, matching ``run_spec``'s final ``{k: v ... if k in
      valid_params}`` filter).

    Parameters
    ----------
    func : callable
        A resolved ``plot_*`` function (e.g. ``spec._resolve_func(...)``).
    params : dict
        Raw form values keyed by spec-style names.

    Returns
    -------
    dict
        Kwargs safe to splat into ``func(experiment, **kwargs)``.
    """
    from PyFLASH.spec import _convert_specificity

    valid_params = set(inspect.signature(func).parameters)
    kwargs = {}
    for key, value in params.items():
        param_key = key
        if (key == "columns"
                and "columns" not in valid_params
                and "filtered_columns" in valid_params):
            param_key = "filtered_columns"
        if key == "specificity":
            value = _convert_specificity(value)
        kwargs[param_key] = value
    return {k: v for k, v in kwargs.items() if k in valid_params}


def run_plot_spec(batch_or_dict, path) -> dict:
    """Validate then run a declarative plot spec file against a batch.

    Thin wrapper over :func:`PyFLASH.spec.load_spec`, ``validate_spec`` and
    ``run_spec`` (house rule 1 — no plotting logic here). Validation runs first;
    **errors block** (the spec is not executed) while **warnings are surfaced**
    and the spec still runs. ``run_spec`` itself catches each entry's exceptions
    and returns ``None`` for failures, so a single bad entry never aborts the
    others — this reports each as ``"ok"`` or ``"failed"`` accordingly.

    Parameters
    ----------
    batch_or_dict
        A single ``Batch``/``Experiment`` or a ``{name: source}`` dict (entries
        select a source via ``batch: name``), exactly as ``run_spec`` accepts.
    path : str
        Path to a ``.yaml`` / ``.json`` / ``.toml`` spec file. (YAML needs
        PyYAML; JSON works with no extra dependency.)

    Returns
    -------
    dict
        On a validation error: ``{"ok": False, "errors": [...],
        "warnings": [...]}`` (nothing was run). Otherwise ``{"ok": True,
        "warnings": [...], "results": ["ok" | "failed", ...]}`` with one entry
        per plot in spec order.
    """
    from PyFLASH.spec import load_spec, run_spec, validate_spec

    spec = load_spec(path)
    errors, warnings = validate_spec(spec, batch_or_dict)
    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings}

    results = run_spec(batch_or_dict, path)
    return {
        "ok": True,
        "warnings": warnings,
        "results": ["ok" if r is not None else "failed" for r in results],
    }


def run_quick_plot(batch, plot_type: str, params: dict):
    """Run one plot type with form *params*, returning whatever the plot returns.

    Resolves the ``plot_*`` function lazily through
    :func:`PyFLASH.spec._resolve_func` (so importing ``services`` never imports
    plotting), filters *params* to the function's signature via
    :func:`_build_plot_kwargs` (``columns`` → ``filtered_columns`` remap,
    ``specificity`` list → tuple conversion, unknown keys dropped), then calls
    ``func(batch, **kwargs)``. Figures are written to ``batch.fig_path`` when the
    function's ``save`` is left True; the return value is plot-specific (most
    ``plot_*`` close the figure and return non-``Figure`` data — embed via the
    saved files located by :mod:`PyFLASH.ui.figures`).

    Parameters
    ----------
    batch
        A loaded ``Batch``/``Experiment``.
    plot_type : str
        A key of ``spec.PLOT_REGISTRY`` (see :func:`available_plots`).
    params : dict
        Raw form values keyed by spec-style names.

    Returns
    -------
    object
        Whatever the underlying ``plot_*`` returns (do not assume a ``Figure``).
    """
    from PyFLASH.spec import PLOT_REGISTRY, _resolve_func

    func = _resolve_func(PLOT_REGISTRY[plot_type])
    kwargs = _build_plot_kwargs(func, params)
    return func(batch, **kwargs)
