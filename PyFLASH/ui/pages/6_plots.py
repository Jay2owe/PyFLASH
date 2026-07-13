"""Plots page — run the standard PyFLASH plots from a spec file or a form.

Reads the ``Batch``/``Experiment`` placed in ``st.session_state["batch"]`` by
the Project or Process page. Two tabs:

* **Spec file** — pick a ``.yaml`` / ``.json`` plot spec, validate it first
  (errors block; warnings are shown), then run it via ``services.run_plot_spec``
  and report each entry as ok / failed. The freshly-saved figures are embedded.
* **Quick plot** — choose a plot type from ``services.available_plots()`` and
  fill a small parameter form for the common ones (``mean_bars``, ``matrices``,
  ``regressions``, ``volcano``, ``histograms``). Image/representative/location
  types route to Stage 08. ``cheat_sheet`` help is shown for the selected type.

All PyFLASH calls go through ``services`` (Streamlit-free) and figure embedding
through ``figures`` (Streamlit imported only inside its renderer). Figures are
read back from ``batch.fig_path`` after the plot saves them — plots do not
reliably return a ``Figure`` (verified at runtime). ``Config.SAVE_MODE`` must be
True for files to be written; a toggle surfaces that.
"""

import contextlib
import io
import os
import time

import streamlit as st

from PyFLASH.config import Config
from PyFLASH.ui import figures, services

st.header("Plots")

batch = st.session_state.get("batch")
if batch is None:
    st.info("No analysis loaded. Open a .pkl on the Project page first, or "
            "build one on the Process page.")
    st.stop()

st.caption(
    f"Working on **{type(batch).__name__}** "
    f"(name: {getattr(batch, 'name', '?')})."
)

fig_path = getattr(batch, "fig_path", None)
if not fig_path:
    st.warning(
        "This object has no `fig_path`; saved figures cannot be located. "
        "Plots may still run but nothing will be embedded."
    )


# ── Shared helpers ──────────────────────────────────────────────────────────


def _save_mode_toggle(key):
    """Render a SAVE_MODE notice + toggle; returns the desired SAVE_MODE bool.

    ``Config.SAVE_MODE`` is process-global and gates ``save_fig``. The UI embeds
    saved files, so it must be True to show anything; expose it so a user who
    only wants a quick on-screen look understands why nothing appears if off.
    """
    return st.toggle(
        "Save figures to disk (required to embed them)",
        value=bool(Config.SAVE_MODE),
        key=key,
        help="Writes 600-dpi SVGs under the batch 'Python Figures' folder. "
             "Must be on for the figures to appear below.",
    )


def _cheat_sheet_text(plot_type):
    """Return ``cheat_sheet`` help for *plot_type* as text (it prints, not returns).

    Resolves the plot's function name from the registry and captures the
    ``cheat_sheet`` stdout. Lazily imports plotting only when help is requested,
    so the page stays light until a user opens the help expander.
    """
    try:
        from PyFLASH.plotting import cheat_sheet
        from PyFLASH.spec import PLOT_REGISTRY
    except Exception as exc:  # pragma: no cover - defensive import guard
        return f"(could not load help: {exc})"

    func_name = PLOT_REGISTRY.get(plot_type, plot_type)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            cheat_sheet(func_name)
        except Exception as exc:  # pragma: no cover - defensive
            return f"(could not render help: {exc})"
    return buf.getvalue()


def _show_help(plot_type):
    """Render the cheat_sheet help for *plot_type* in an expander."""
    with st.expander(f"Parameter help — {plot_type}"):
        st.code(_cheat_sheet_text(plot_type), language="text")


def _csv_list(raw):
    """Split a comma-separated text field into a clean list (or ``None``)."""
    return [s.strip() for s in (raw or "").split(",") if s.strip()] or None


def _parse_filter_by(raw):
    """Parse a 'Key, Value[, Value...]' row-filter field into a list (or None).

    Returns the raw token list (e.g. ``["Time", "WeekEight"]``);
    ``services.run_quick_plot`` converts it to the tuple form core expects.
    Multi-filter queues are out of scope for the form.
    """
    return _csv_list(raw)


def _run_and_embed(plot_type, params, save_mode):
    """Run a quick plot and embed its saved figures, with SAVE_MODE handling.

    Captures the time just before running so only this run's figures are
    embedded, temporarily applies the SAVE_MODE toggle (restoring it after),
    runs inside ``services.capture_output`` for a readable log, and renders the
    located figures via ``figures.embed_figure``.
    """
    prev_save_mode = Config.SAVE_MODE
    Config.SAVE_MODE = bool(save_mode)
    started = time.time()
    with st.status(f"Running {plot_type}…", expanded=True) as status:
        try:
            with services.capture_output() as buf:
                result = services.run_quick_plot(batch, plot_type, params)
        except Exception as exc:
            status.update(label=f"{plot_type} failed", state="error")
            st.exception(exc)
            return
        finally:
            Config.SAVE_MODE = prev_save_mode
        log = buf.getvalue()
        if log.strip():
            st.code(log)
        status.update(label=f"{plot_type} complete", state="complete")

    if not save_mode:
        st.info(
            "Saving was off, so no figure files were written to embed. Turn "
            "on 'Save figures to disk' to see them here."
        )
        return

    embedded = figures.embed_figure(
        result, fig_path, since=started,
        caption="Figures saved by this run:",
    )
    if not embedded:
        st.warning(
            "The plot ran but no new figure files were found under the batch "
            "figure folder. It may have produced data only (e.g. a dry run) or "
            "skipped all columns — see the log above."
        )


# ── Tabs ────────────────────────────────────────────────────────────────────

tab_spec, tab_quick = st.tabs(["Spec file", "Quick plot"])


# ── Tab: Spec file ──────────────────────────────────────────────────────────

with tab_spec:
    st.subheader("Run a plot spec")
    st.caption(
        "Provide a declarative `.yaml` / `.json` spec (a `plots:` list of "
        "entries, each with a `type` and parameters). It is validated first — "
        "errors block, warnings are shown — then run; each entry reports "
        "ok / failed independently."
    )

    spec_path = st.text_input(
        "Spec file path",
        value="",
        help="Path to a .yaml or .json spec on this machine. YAML needs PyYAML "
             "installed; JSON always works.",
    )
    uploaded = st.file_uploader(
        "…or upload a spec file", type=["yaml", "yml", "json"],
        help="Uploaded specs are written to a temp file before running.",
    )

    spec_save_mode = _save_mode_toggle("spec_save_mode")
    run_spec_clicked = st.button("Validate & run spec", type="primary")

    if run_spec_clicked:
        path = None
        tmp_to_clean = None
        if uploaded is not None:
            suffix = os.path.splitext(uploaded.name)[1] or ".json"
            tmp_dir = st.session_state.get("_spec_tmp_dir")
            if not tmp_dir:
                import tempfile
                tmp_dir = tempfile.mkdtemp(prefix="pyflash_spec_")
                st.session_state["_spec_tmp_dir"] = tmp_dir
            path = os.path.join(tmp_dir, uploaded.name)
            with open(path, "wb") as fh:
                fh.write(uploaded.getbuffer())
        elif spec_path.strip():
            path = spec_path.strip()

        if not path:
            st.warning("Enter a spec file path or upload a file.")
        elif not os.path.isfile(path):
            st.error(f"Spec file not found: {path}")
        else:
            prev_save_mode = Config.SAVE_MODE
            Config.SAVE_MODE = bool(spec_save_mode)
            started = time.time()
            try:
                with st.status("Validating & running spec…", expanded=True) \
                        as status:
                    try:
                        with services.capture_output() as buf:
                            outcome = services.run_plot_spec(batch, path)
                    except Exception as exc:
                        status.update(label="Spec run failed", state="error")
                        st.exception(exc)
                        outcome = None
                    else:
                        log = buf.getvalue()
                        if log.strip():
                            st.code(log)
                        status.update(label="Spec finished", state="complete")
            finally:
                Config.SAVE_MODE = prev_save_mode

            if outcome is not None:
                for w in outcome.get("warnings", []):
                    st.warning(w)

                if not outcome["ok"]:
                    st.error(
                        f"Spec validation failed with "
                        f"{len(outcome['errors'])} error(s) — nothing was run."
                    )
                    for e in outcome["errors"]:
                        st.markdown(f"- {e}")
                else:
                    results = outcome["results"]
                    n_ok = sum(1 for r in results if r == "ok")
                    n_failed = len(results) - n_ok
                    if n_failed:
                        st.warning(
                            f"{n_ok} entry(ies) ok, {n_failed} failed "
                            "(failed entries are reported, not fatal)."
                        )
                    else:
                        st.success(f"All {n_ok} plot entry(ies) ran.")
                    for i, r in enumerate(results):
                        icon = "✅" if r == "ok" else "❌"
                        st.markdown(f"{icon} `plots[{i}]` — {r}")

                    if spec_save_mode:
                        figures.embed_figure(
                            None, fig_path, since=started,
                            caption="Figures saved by this spec run:",
                        )


# ── Tab: Quick plot ─────────────────────────────────────────────────────────

# Form builders for the common plot types. Each returns a params dict keyed by
# spec-style names; services._build_plot_kwargs maps/filters them to the real
# signature (e.g. 'columns' -> 'filtered_columns', filter_by list -> tuple).

FORM_TYPES = ("mean_bars", "matrices", "regressions", "volcano", "histograms")


def _common_filter_factor():
    """Shared row-filter + factor inputs used by several forms."""
    filter_raw = st.text_input(
        "Filter by (Key, Value)", value="",
        help="Optional row filter, e.g. 'Time, WeekEight'. Converted to a "
             "tuple before the plot is called.",
        key="qp_filter_by",
    )
    factor = st.text_input(
        "Factor (grouping column)", value="",
        help="Optional column to group by instead of the full group design.",
        key="qp_factor",
    ).strip() or None
    return _parse_filter_by(filter_raw), factor


def _form_columns_based(label):
    """Form for the data-column plots (mean_bars / volcano / matrices)."""
    columns = _csv_list(st.text_input(
        "Columns (exact names, comma-separated)", value="",
        help="Leave blank to use column-name contains filters or all numeric columns.",
        key=f"qp_{label}_columns",
    ))
    column_strings = _csv_list(st.text_input(
        "Column name contains (comma-separated)", value="",
        help="Keep columns whose name contains any of these substrings.",
        key=f"qp_{label}_colstrings",
    ))
    exclude = st.text_input(
        "Exclude columns containing", value="",
        key=f"qp_{label}_exclude",
    ).strip()
    filter_by, factor = _common_filter_factor()
    params = {}
    if columns:
        params["data_cols"] = columns
    if column_strings:
        params["data_col_contains"] = column_strings
    if exclude:
        params["data_col_exclude"] = exclude
    if filter_by:
        params["filter_by"] = filter_by
    if factor:
        params["factor"] = factor
    return params


def _form_mean_bars():
    params = _form_columns_based("mean_bars")
    params["points"] = st.toggle("Overlay data points", value=True,
                                 key="qp_mean_bars_points")
    params["normalize"] = st.toggle("Normalize", value=False,
                                    key="qp_mean_bars_normalize")
    return params


def _form_volcano():
    params = _form_columns_based("volcano")
    control = st.text_input(
        "Control group (optional)", value="", key="qp_volcano_control",
    ).strip()
    if control:
        params["control"] = control
    return params


def _form_matrices():
    params = _form_columns_based("matrices")
    correlation = st.selectbox(
        "Correlation", ["pearsonr", "spearmanr", "kendalltau"],
        index=0, key="qp_matrices_correlation",
    )
    params["correlation"] = correlation
    marker = st.text_input("Marker (optional)", value="",
                           key="qp_matrices_marker").strip()
    if marker:
        params["marker"] = marker
    return params


def _form_regressions():
    x = st.text_input("X column", value="", key="qp_reg_x").strip()
    y = st.text_input("Y column", value="", key="qp_reg_y").strip()
    test = st.selectbox(
        "Test", ["pearsonr", "spearmanr", "kendalltau"],
        index=0, key="qp_reg_test",
    )
    filter_by, factor = _common_filter_factor()
    params = {"test": test}
    if x:
        params["x"] = x
    if y:
        params["y"] = y
    if filter_by:
        params["filter_by"] = filter_by
    if factor:
        params["factor"] = factor
    return params


def _form_histograms():
    marker = st.text_input("Marker", value="", key="qp_hist_marker").strip()
    x_attr = st.text_input("X attribute", value="", key="qp_hist_xattr").strip()
    bins = st.number_input("Bins", min_value=1, max_value=1000, value=30,
                           step=1, key="qp_hist_bins")
    kde = st.toggle("KDE overlay", value=False, key="qp_hist_kde")
    filter_by, factor = _common_filter_factor()
    params = {"bins": int(bins), "kde": kde}
    if marker:
        params["marker"] = marker
    if x_attr:
        params["x_attr"] = x_attr
    if filter_by:
        params["filter_by"] = filter_by
    if factor:
        params["factor"] = factor
    return params


FORM_BUILDERS = {
    "mean_bars": _form_mean_bars,
    "matrices": _form_matrices,
    "regressions": _form_regressions,
    "volcano": _form_volcano,
    "histograms": _form_histograms,
}


with tab_quick:
    st.subheader("Quick plot")
    st.caption(
        "Pick a plot type and fill in the parameters. Forms cover the common "
        "types; other (non-image) types run with their defaults."
    )

    plot_types = services.available_plots()
    default_index = plot_types.index("mean_bars") \
        if "mean_bars" in plot_types else 0
    plot_type = st.selectbox("Plot type", plot_types, index=default_index)

    _show_help(plot_type)

    if plot_type in services.IMAGE_PLOT_TYPES:
        st.info(
            f"**{plot_type}** needs imported images / object locations and is "
            "handled by the Image tools page (Stage 08). Use that page once it "
            "is available."
        )
    else:
        if plot_type in FORM_BUILDERS:
            params = FORM_BUILDERS[plot_type]()
        else:
            params = {}
            st.caption(
                f"No guided form for **{plot_type}** yet — it will run with its "
                "default parameters. Use a spec file for full control."
            )

        quick_save_mode = _save_mode_toggle("quick_save_mode")

        if st.button("Run plot", type="primary", key="run_quick"):
            _run_and_embed(plot_type, params, quick_save_mode)
