"""Images page — browse image grids, representative panels and location maps.

Reads the ``Batch``/``Experiment`` placed in ``st.session_state["batch"]`` by
the Project or Process page. Three sections:

* **Browse** — ``plot_images`` grid filtered by markers / subject / ROI, with
  tile and fast-loading options. Saved to ``batch.fig_path`` and embedded via
  the Stage 07 figure helper.
* **Representative panels** — ``plot_representative_images`` for the chosen
  markers, plus a ``st.data_editor`` view/editor of the
  ``batch.representative_images`` selection table. Edits are stored back onto
  the object via ``services.set_representative_selections``; *saving them to
  disk* is the Stage-06 "Save analysis (.pkl)" control on the Export page, and
  the selections carry over on the next ``create_batch(rerun=True)``.
* **Locations** — ``plot_locations`` for a chosen experiment and object marker.

Image actions are disabled with a clear message when no ``Images/`` folder was
found (``services.image_table`` returns ``None``).

Interactive ``select_representative_images`` (matplotlib click-to-pick) is
**deliberately not wired** here — it is event-driven and not web-portable, so
representative selection stays table-based in this page and interactive picking
stays in the notebook (see the deferral note rendered below). All PyFLASH calls
go through ``services`` (Streamlit-free); figure embedding goes through
``figures`` (Streamlit imported only inside its renderer). Streamlit is imported
here (a page), never in ``services.py``.
"""

import time

import streamlit as st

from PyFLASH.config import Config
from PyFLASH.ui import figures, services

st.header("Images")

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
        "Image plots may still run but nothing will be embedded."
    )


# ── Shared helpers ──────────────────────────────────────────────────────────


def _save_mode_toggle(key):
    """Render a SAVE_MODE notice + toggle; returns the desired SAVE_MODE bool.

    ``Config.SAVE_MODE`` is process-global and gates figure saving. The UI
    embeds saved files, so it must be True to show anything; expose it so a user
    understands why nothing appears if it is off.
    """
    return st.toggle(
        "Save figures to disk (required to embed them)",
        value=bool(Config.SAVE_MODE),
        key=key,
        help="Writes high-DPI figures under the batch 'Python Figures' folder. "
             "Must be on for the images to appear below.",
    )


def _csv_list(raw):
    """Split a comma-separated text field into a clean list (or ``None``)."""
    return [s.strip() for s in (raw or "").split(",") if s.strip()] or None


def _run_and_embed(label, runner, save_mode, *args, **kwargs):
    """Run an image plot through *runner* and embed its saved figures.

    Captures the time just before running so only this run's figures are
    embedded, temporarily applies the SAVE_MODE toggle (restoring it after),
    runs inside ``services.capture_output`` for a readable log, then renders the
    located figures via ``figures.embed_figure``. ``args``/``kwargs`` forward to
    *runner* (a ``services.run_*`` wrapper).
    """
    prev_save_mode = Config.SAVE_MODE
    Config.SAVE_MODE = bool(save_mode)
    started = time.time()
    with st.status(f"Running {label}…", expanded=True) as status:
        try:
            with services.capture_output() as buf:
                result = runner(*args, **kwargs)
        except ValueError as exc:
            # Expected, user-actionable (e.g. "No imported images were found",
            # "No images matched the requested … filters").
            status.update(label=f"{label} failed", state="error")
            st.error(str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive UI guard
            status.update(label=f"{label} failed", state="error")
            st.exception(exc)
            return
        finally:
            Config.SAVE_MODE = prev_save_mode
        log = buf.getvalue()
        if log.strip():
            st.code(log)
        status.update(label=f"{label} complete", state="complete")

    if not save_mode:
        st.info(
            "Saving was off, so no figure files were written to embed. Turn on "
            "'Save figures to disk' to see them here."
        )
        return

    embedded = figures.embed_figure(
        result, fig_path, since=started,
        caption="Figures saved by this run:",
    )
    if not embedded:
        st.warning(
            "The plot ran but no new figure files were found under the batch "
            "figure folder. It may have produced data only, or all images were "
            "filtered out — see the log above."
        )


# ── Image availability gate ─────────────────────────────────────────────────

images_df = services.image_table(batch)

if images_df is None:
    st.warning(
        "No imported images are available for this analysis (no `Images/` "
        "folder was found, or images were not imported during processing). "
        "Image, representative-panel and location tools are disabled.\n\n"
        "To enable them, rebuild the batch on the Process page with "
        "**Import images** turned on."
    )
    st.stop()

with st.expander("Imported images", expanded=False):
    st.caption(
        f"{len(images_df)} image(s) found. This is the table populated by "
        "`importImages`; the tools below render and filter it."
    )
    st.dataframe(images_df, use_container_width=True, hide_index=True)


# ── Tabs ────────────────────────────────────────────────────────────────────

tab_browse, tab_rep, tab_loc = st.tabs(
    ["Browse", "Representative panels", "Locations"]
)


# ── Tab: Browse ─────────────────────────────────────────────────────────────

with tab_browse:
    st.subheader("Browse image grid")
    st.caption(
        "Render a grid of imported images (`plot_images`), optionally filtered "
        "by marker, subject and ROI."
    )

    br_markers = _csv_list(st.text_input(
        "Markers (comma-separated, blank = all)", value="",
        key="img_browse_markers",
        help="Exact marker names to include, e.g. 'DAPI, mCherry'.",
    ))
    col_a, col_r = st.columns(2)
    br_subject = col_a.text_input(
        "Subject filter (substring)", value="", key="img_browse_subject",
    ).strip() or None
    br_roi = col_r.text_input(
        "ROI filter (substring)", value="", key="img_browse_roi",
    ).strip() or None

    col_t, col_m = st.columns(2)
    br_tile = col_t.number_input(
        "Tile size", min_value=1.0, max_value=20.0, value=4.0, step=0.5,
        key="img_browse_tile",
        help="Inches per image tile in the grid.",
    )
    br_max = col_m.number_input(
        "Max images (0 = all)", min_value=0, max_value=10000, value=0, step=1,
        key="img_browse_max",
        help="Cap the number of tiles to keep large grids responsive.",
    )

    col_f, col_p = st.columns(2)
    br_fast = col_f.toggle(
        "Fast loading", value=False, key="img_browse_fast",
        help="Downsample large TIFFs on load to save memory.",
    )
    br_preview = col_p.number_input(
        "Preview max dimension (px, 0 = off)", min_value=0, max_value=8192,
        value=0, step=64, key="img_browse_preview",
        help="With fast loading, cap the longest image side to this many "
             "pixels.",
    )
    br_scalebar = st.toggle(
        "Draw scale bar", value=False, key="img_browse_scalebar",
        help=f"Scale bars use Config.PIXEL_SIZE (currently "
             f"{getattr(Config, 'PIXEL_SIZE', '?')} microns/pixel).",
    )

    browse_save_mode = _save_mode_toggle("img_browse_save")

    if st.button("Render grid", type="primary", key="img_browse_run"):
        kw = {
            "subject_filter": br_subject,
            "roi_filter": br_roi,
            "tile_size": float(br_tile),
            "fast_loading": bool(br_fast),
            "scale_bar": bool(br_scalebar),
        }
        if br_max:
            kw["max_images"] = int(br_max)
        if br_preview:
            kw["preview_max_dim"] = int(br_preview)
        _run_and_embed(
            "image grid", services.run_image_grid, browse_save_mode,
            batch, br_markers, **kw,
        )


# ── Tab: Representative panels ───────────────────────────────────────────────

with tab_rep:
    st.subheader("Representative panels")
    st.caption(
        "Render representative-image panels (`plot_representative_images`) for "
        "the chosen markers, and view/edit the saved selection table below."
    )

    # --- selection table editor -------------------------------------------------
    st.markdown("**Representative selection table**")
    selections = services.get_representative_selections(batch)
    has_selection = selections is not None and not getattr(
        selections, "empty", False
    )
    if not has_selection:
        st.info(
            "No representative images have been selected yet. Selections are "
            "made interactively in the notebook (see the note below) and then "
            "carried over to this analysis; once present they appear here for "
            "viewing and editing."
        )
    else:
        st.caption(
            "Edit the table to add, remove or relabel selections. Edits are "
            "stored on the in-memory analysis when you click **Apply edits**; "
            "use the Export page's **Save analysis (.pkl)** to persist them to "
            "disk. They are also carried over automatically on the next "
            "reprocess (`create_batch(rerun=True)`)."
        )
        edited = st.data_editor(
            selections,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            key="rep_editor",
        )
        if st.button("Apply edits", key="rep_apply"):
            services.set_representative_selections(batch, edited)
            st.session_state["batch"] = batch
            st.success(
                "Selections updated on the in-memory analysis. Save the .pkl "
                "on the Export page to keep them."
            )

    st.divider()

    # --- render panels ----------------------------------------------------------
    st.markdown("**Render panels**")
    rep_markers = _csv_list(st.text_input(
        "Markers (comma-separated, blank = all)", value="",
        key="img_rep_markers",
        help="Exact marker names whose representative panels to render.",
    ))
    rep_subject = st.text_input(
        "Subject filter (substring)", value="", key="img_rep_subject",
    ).strip() or None
    col_rf, col_rp = st.columns(2)
    rep_fast = col_rf.toggle(
        "Fast loading", value=False, key="img_rep_fast",
        help="Downsample large TIFFs on load to save memory.",
    )
    rep_preview = col_rp.number_input(
        "Preview max dimension (px, 0 = off)", min_value=0, max_value=8192,
        value=0, step=64, key="img_rep_preview",
    )

    rep_save_mode = _save_mode_toggle("img_rep_save")

    if st.button("Render panels", type="primary", key="img_rep_run"):
        if not has_selection:
            st.warning(
                "There are no representative selections to render. Make "
                "selections in the notebook first; they will carry over here."
            )
        else:
            kw = {"subject_filter": rep_subject, "fast_loading": bool(rep_fast)}
            if rep_preview:
                kw["preview_max_dim"] = int(rep_preview)
            _run_and_embed(
                "representative panels", services.run_representative_panels,
                rep_save_mode, batch, rep_markers, **kw,
            )

    # --- deferral note ----------------------------------------------------------
    st.divider()
    st.info(
        "**Interactive selection is not available in this UI.** "
        "`select_representative_images` uses matplotlib click-to-pick, which is "
        "event-driven and does not port to the browser. It stays in the "
        "notebook for now; this page only views and edits the resulting "
        "selection table. A web-portable (or PySide6) selection flow may be "
        "added later."
    )


# ── Tab: Locations ───────────────────────────────────────────────────────────

with tab_loc:
    st.subheader("Location maps")
    st.caption(
        "Render a spatial scatter map (`plot_locations`) for one experiment. "
        "`plot_locations` takes a single Experiment, so pick it explicitly."
    )

    experiments = list(getattr(batch, "experiment_list", None) or [])
    # An Experiment loaded directly (not a Batch) is its own single source.
    if not experiments and hasattr(batch, "data"):
        experiments = [batch]

    if not experiments:
        st.info(
            "No experiments are available on this object to plot locations for."
        )
    else:
        exp_names = [getattr(e, "name", f"experiment {i}")
                     for i, e in enumerate(experiments)]
        chosen_name = st.selectbox(
            "Experiment", exp_names, index=0, key="img_loc_exp",
        )
        chosen_exp = experiments[exp_names.index(chosen_name)]

        loc_objects = _csv_list(st.text_input(
            "Object markers (comma-separated)", value="",
            key="img_loc_objects",
            help="Marker columns to plot as object locations, e.g. 'CK1d'. "
                 "Required.",
        ))
        col_sep, col_join = st.columns(2)
        loc_group_options = {"Groups": "groups", "Subjects": "subjects"}
        loc_separate_label = col_sep.selectbox(
            "Separate by", list(loc_group_options), index=0,
            key="img_loc_separate",
        )
        loc_join_label = col_join.selectbox(
            "Join by", ["Subjects", "Groups"], index=0,
            key="img_loc_join",
        )
        col_co, col_an = st.columns(2)
        loc_coloc = col_co.toggle(
            "Colocalise", value=True, key="img_loc_coloc",
        )
        loc_annotate = col_an.toggle(
            "Annotate panels", value=True, key="img_loc_annotate",
        )

        loc_save_mode = _save_mode_toggle("img_loc_save")

        if st.button("Render locations", type="primary", key="img_loc_run"):
            if not loc_objects:
                st.warning("Enter at least one object marker to plot.")
            else:
                kw = {
                    "separate_by": loc_group_options[loc_separate_label],
                    "join_by": loc_group_options[loc_join_label],
                    "colocalise": bool(loc_coloc),
                    "annotate": bool(loc_annotate),
                }
                _run_and_embed(
                    "locations", services.run_locations, loc_save_mode,
                    chosen_exp, loc_objects, **kw,
                )
