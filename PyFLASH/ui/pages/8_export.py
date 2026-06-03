"""Export page — write the formatted Excel workbooks and save the analysis.

Reads the ``Batch``/``Experiment`` placed in ``st.session_state["batch"]`` by
the Project or Process page. Exposes the two "finish the job" actions from the
notebook as forms:

* **Export Excel** — toggles for the three workbooks (``if_summary`` /
  ``if_extended`` / ``behaviour``), an include + exclude column regex per
  workbook, an optional ``save_name`` per workbook, and a target ``save_path``
  (defaults to the batch ``Exports/`` folder). Calls
  ``services.export_excel`` inside ``st.status`` and renders the captured log,
  the produced ``.xlsx`` files, and the ``*_RegexFilters.txt`` reports so users
  can see what was matched / skipped.
* **Save state** — a filename field + button calling ``services.save_batch``
  (default ``<pickle dir>/<name>.pkl``).

Regex is pre-validated with ``services.validate_regex`` and a friendly error is
shown *before* export is attempted. All PyFLASH calls go through ``services``
(Streamlit-free); Streamlit is imported here (a page), never in ``services.py``.
"""

import os

import streamlit as st

from PyFLASH.ui import services

st.header("Export & Save")

batch = st.session_state.get("batch")
if batch is None:
    st.info("No analysis loaded. Open a .pkl on the Project page first, or "
            "build one on the Process page.")
    st.stop()

st.caption(
    f"Working on **{type(batch).__name__}** "
    f"(name: {getattr(batch, 'name', '?')})."
)


# ── Helpers ─────────────────────────────────────────────────────────────────


def _split_patterns(raw):
    """Split a comma-separated regex field into a clean list (or ``None``)."""
    return [s.strip() for s in (raw or "").split(",") if s.strip()] or None


def _default_export_path():
    """Best-effort default for the export folder: the batch ``Exports/`` dir."""
    path = getattr(batch, "export_path", None)
    if not path:
        file_path = getattr(batch, "filePath", None)
        if file_path:
            path = os.path.join(file_path, "Exports")
    return path or ""


def _default_save_filename():
    """Default save-state path: ``<pickle dir>/<name>.pkl``.

    Prefers the directory of the last load/save path (``_state_path``), then the
    batch ``csv_path`` (``save_state``'s own default), so re-saving lands beside
    the existing pickle.
    """
    name = getattr(batch, "name", "batch") or "batch"
    state_path = getattr(batch, "_state_path", None)
    if state_path:
        return os.path.join(os.path.dirname(state_path), f"{name}.pkl")
    csv_path = getattr(batch, "csv_path", None)
    if csv_path:
        return os.path.join(csv_path, f"{name}.pkl")
    return f"{name}.pkl"


def _list_outputs(root):
    """Return the .xlsx workbooks and *_RegexFilters.txt reports under *root*.

    Walked read-only after export so the page can show what was produced and
    surface the regex reports (the workbooks live in per-ROI subfolders).
    """
    workbooks, reports = [], []
    if not root or not os.path.isdir(root):
        return workbooks, reports
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            if fn.lower().endswith(".xlsx"):
                workbooks.append(full)
            elif fn.endswith("_RegexFilters.txt"):
                reports.append(full)
    return sorted(workbooks), sorted(reports)


# ── Export Excel ────────────────────────────────────────────────────────────

st.subheader("Export Excel")
st.caption(
    "Pick which workbooks to write and (optionally) narrow the exported "
    "metric columns with regular expressions. Include keeps only matching "
    "columns; exclude drops matching columns (both case-insensitive)."
)

WORKBOOKS = [
    ("if_summary", "IF Summary", "IF_Summary"),
    ("if_extended", "IF Extended", "IF_Extended"),
    ("behaviour", "Behaviour Summary", "Behavior_Summary"),
]

toggles, includes, excludes, save_names = {}, {}, {}, {}
for key, label, default_name in WORKBOOKS:
    with st.expander(label, expanded=True):
        toggles[key] = st.toggle(
            f"Export {label}", value=True, key=f"toggle_{key}")
        includes[key] = st.text_input(
            "Include columns matching (regex, comma-separated)",
            value="", key=f"include_{key}",
            disabled=not toggles[key],
            help="Leave blank to keep all columns.",
        )
        excludes[key] = st.text_input(
            "Exclude columns matching (regex, comma-separated)",
            value="", key=f"exclude_{key}",
            disabled=not toggles[key],
            help="Leave blank to exclude nothing.",
        )
        save_names[key] = st.text_input(
            "Workbook file name (without .xlsx)",
            value=default_name, key=f"savename_{key}",
            disabled=not toggles[key],
        )

save_path = st.text_input(
    "Export folder",
    value=_default_export_path(),
    help="Where the workbooks are written. Leave blank to use the batch "
         "Exports/ folder. A relative path lands under Exports/; an absolute "
         "path is used as-is.",
)

export = st.button("Export", type="primary")

if export:
    if not any(toggles.values()):
        st.warning("Select at least one workbook to export.")
        st.stop()

    # Pre-validate every regex field so a typo shows a friendly error before we
    # start a (possibly slow) export, rather than failing mid-write.
    include_lists = {k: _split_patterns(includes[k]) for k in toggles}
    exclude_lists = {k: _split_patterns(excludes[k]) for k in toggles}
    regex_error = None
    for key, label, _default in WORKBOOKS:
        if not toggles[key]:
            continue
        for kind, lst in (("include", include_lists[key]),
                          ("exclude", exclude_lists[key])):
            try:
                services.validate_regex(lst)
            except Exception as exc:  # re.error
                regex_error = f"Invalid {label} {kind} regex: {exc}"
                break
        if regex_error:
            break

    if regex_error:
        st.error(regex_error)
        st.stop()

    # A blank save_name means "use the default workbook name" — pass None so
    # core falls back to its default stem (batch.py:_resolve_export_stem).
    def _name(key):
        return (save_names[key].strip() or None) if toggles[key] else None

    target = save_path.strip() or None

    with st.status("Exporting…", expanded=True) as status:
        st.caption("Running export_all_excel — progress is captured below.")
        try:
            log = services.export_excel(
                batch,
                save_path=target,
                if_summary=toggles["if_summary"],
                if_extended=toggles["if_extended"],
                behaviour=toggles["behaviour"],
                if_summary_include=include_lists["if_summary"],
                if_extended_include=include_lists["if_extended"],
                behaviour_include=include_lists["behaviour"],
                if_summary_exclude=exclude_lists["if_summary"],
                if_extended_exclude=exclude_lists["if_extended"],
                behaviour_exclude=exclude_lists["behaviour"],
            )
        except ValueError as exc:
            # Expected, user-actionable (bad regex re-raised by core, etc.).
            status.update(label="Export failed", state="error")
            st.error(str(exc))
        except PermissionError as exc:
            # Known risk: an open .xlsx locks the file on Windows.
            status.update(label="Export failed", state="error")
            st.error(
                "Could not write a workbook — it may be open in Excel. Close "
                f"it and try again. ({exc})"
            )
        except Exception as exc:  # pragma: no cover - defensive UI guard
            status.update(label="Export failed", state="error")
            st.exception(exc)
        else:
            if log.strip():
                st.code(log)
            else:
                st.caption("(no progress output was captured)")
            status.update(label="Export complete", state="complete")

            resolved_root = target if (target and os.path.isabs(target)) \
                else _default_export_path()
            workbooks, reports = _list_outputs(resolved_root)
            if workbooks:
                st.success(f"Wrote {len(workbooks)} workbook(s).")
                st.markdown("**Workbooks:**")
                for wb in workbooks:
                    st.markdown(f"- `{wb}`")
            else:
                st.caption(
                    "No workbooks found under the export folder — check the "
                    "log above (a missing behaviour table is skipped silently)."
                )

            for report in reports:
                with st.expander(f"Regex report — {os.path.basename(report)}"):
                    try:
                        with open(report, encoding="utf-8") as fh:
                            st.code(fh.read())
                    except OSError as exc:  # pragma: no cover - defensive
                        st.caption(f"Could not read report: {exc}")


# ── Save state ──────────────────────────────────────────────────────────────

st.divider()
st.subheader("Save analysis (.pkl)")
st.caption(
    "Write the in-memory analysis to a pickle so it can be re-opened later "
    "from the Project page without reprocessing."
)

save_filename = st.text_input(
    "Save file",
    value=_default_save_filename(),
    help="Destination .pkl path. Defaults beside the existing pickle / cache.",
)

if st.button("Save"):
    target = save_filename.strip()
    if not target:
        st.warning("Enter a file path to save to.")
    else:
        try:
            written = services.save_batch(batch, target)
        except PermissionError as exc:
            st.error(
                "Could not write the pickle — the file may be open or locked. "
                f"({exc})"
            )
        except Exception as exc:  # pragma: no cover - defensive UI guard
            st.exception(exc)
        else:
            st.success(f"Saved to `{written}`")
