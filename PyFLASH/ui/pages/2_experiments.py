"""Experiments page — pick folders and pre-flight validate them.

Lets the user choose experiment folders either by *auto-discovering* the
subfolders of a root (``batch_path``) or by *manually* mapping experiment names
to folders. Each candidate is validated against the exact rule ``create_batch``
uses (replicated read-only in ``services``), so path typos and bad layouts are
caught here — before a long processing run on the Batch page (Stage 05).

This page is strictly read-only on data folders: it never creates Results/ or
Exports/. Streamlit is imported here (a page), never in ``services.py``.
"""

import os

import streamlit as st

from PyFLASH.config import Config
from PyFLASH.ui import dialogs, services
from PyFLASH.ui.project_io import Project

# Surface a hint when a chosen path is long (save_fig warns >245 chars).
_LONG_PATH_HINT = 245


def _project() -> Project:
    """Return the session Project, creating a fresh one on first visit."""
    proj = st.session_state.get("project")
    if not isinstance(proj, Project):
        proj = Project()
        st.session_state["project"] = proj
    return proj


def _folder_field(label, value, key, help=None):
    """Text input + a "Browse…" button that opens a native folder dialog.

    Falls back to the typed path when tkinter is unavailable (``pick_directory``
    returns ``None``). Returns the current path string.
    """
    col_path, col_browse = st.columns([4, 1])
    path = col_path.text_input(label, value=value or "", key=f"{key}_text",
                               help=help)
    if col_browse.button("Browse…", key=f"{key}_browse"):
        picked = dialogs.pick_directory(initial=path or None)
        if picked:
            st.session_state[f"{key}_text"] = picked
            path = picked
            st.rerun()
        else:
            st.caption("Folder dialog unavailable — type the path above.")
    if path and len(path) > _LONG_PATH_HINT:
        st.warning(
            f"This path is {len(path)} characters long. Very long paths can "
            "trip Windows limits when figures are saved later."
        )
    return path


st.header("Experiments")
st.caption(
    "Point at your experiment folders and check each one matches the layout "
    "create_batch expects, before building a batch."
)

project = _project()

mode = st.radio(
    "How do you want to choose experiment folders?",
    ["Auto-discover from a root folder", "Manual (name → folder)"],
    index=0 if not project.experiments else 1,
    horizontal=True,
)

# ── Folder / processing inputs ──────────────────────────────────────────────

batch_path = _folder_field(
    "Batch root folder (batch_path)",
    project.batch_path,
    key="batch_path",
    help="Parent folder of the experiment subfolders, and where results are "
         "written during processing.",
)

pickle_path = _folder_field(
    "Pickle cache folder (pickle_path)",
    project.pickle_path,
    key="pickle_path",
    help="Where a cached <name>.pkl is read from / written to. Optional.",
)

col_thr, col_img = st.columns([2, 2])
threshold = col_thr.number_input(
    "Threshold",
    min_value=0,
    value=int(project.threshold or Config.THRESHOLD),
    step=1,
    help="Object size/intensity threshold passed to each Experiment "
         f"(Config.THRESHOLD default = {Config.THRESHOLD}).",
)
import_images = col_img.toggle(
    "Import images",
    value=bool(project.import_images),
    help="Load microscopy images from each Images/ folder during processing. "
         "Turn off for a faster, numbers-only run.",
)

# ── Build the list of (name, path) candidates per the chosen mode ───────────

records = []  # validation dicts, each with a "name" key
experiments_map = {}  # name -> entered path, persisted for manual mode

if mode.startswith("Auto"):
    st.subheader("Discovered experiments")
    if not batch_path:
        st.info("Enter a batch root folder above to discover experiments.")
    elif not os.path.isdir(services.check_directory(batch_path) or batch_path):
        st.error("That root folder does not exist or is not a directory.")
    else:
        try:
            records = services.discover_experiments(batch_path)
        except Exception as exc:  # pragma: no cover - defensive UI guard
            st.error(f"Could not scan root folder: {exc}")
            records = []
        if not records:
            st.warning("No subfolders found in that root.")
else:
    st.subheader("Experiment folders")
    st.caption("Add one row per experiment: a name and its folder path.")
    seed = (
        [{"name": n, "path": p} for n, p in project.experiments.items()]
        or [{"name": "", "path": ""}]
    )
    edited = st.data_editor(
        seed,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "name": st.column_config.TextColumn("Experiment name"),
            "path": st.column_config.TextColumn("Folder path"),
        },
        key="experiments_editor",
    )
    for row in edited:
        name = (row.get("name") or "").strip()
        path = (row.get("path") or "").strip()
        if not name and not path:
            continue
        experiments_map[name or path] = path
        rec = services.validate_experiment_folder(path) if path else {
            "path": path, "valid": False, "reason": "no folder entered",
            "has_images": False,
            "layout": {d: False for d in services.LAYOUT_DIRS},
        }
        rec["name"] = name or "(unnamed)"
        records.append(rec)

# ── Validation table + per-folder layout checklist ──────────────────────────

if records:
    st.subheader("Validation")
    table_rows = []
    for rec in records:
        row = {
            "Experiment": rec.get("name", ""),
            "Valid": "✓" if rec["valid"] else "✗",
            "Reason": rec["reason"],
        }
        for d in services.LAYOUT_DIRS:
            row[d] = "✓" if rec["layout"].get(d) else "—"
        table_rows.append(row)
    st.dataframe(table_rows, use_container_width=True, hide_index=True)

    n_valid = sum(1 for r in records if r["valid"])
    st.caption(f"{n_valid} of {len(records)} folder(s) valid.")

    missing_images = [r["name"] for r in records if r["valid"]
                      and not r["has_images"]]
    if missing_images:
        st.warning(
            "No Images/ folder in: " + ", ".join(missing_images) + ". "
            "These can still be processed, but image plots will be disabled "
            "for them later."
        )

# ── Persist choices into the session Project ────────────────────────────────

if st.button("Save selections", type="primary"):
    project.batch_path = batch_path
    project.pickle_path = pickle_path
    project.threshold = int(threshold)
    project.import_images = bool(import_images)
    if mode.startswith("Manual"):
        project.experiments = experiments_map
    else:
        # Auto-discover mode: experiments are derived from batch_path at build
        # time, so keep the mapping empty (create_batch takes the root string).
        project.experiments = {}
    # Keep the flat list in sync for any consumer that wants just the paths.
    project.experiment_paths = [r["path"] for r in records if r.get("path")]
    st.session_state["project"] = project
    st.success("Saved to the current project (persists across pages).")

st.caption(
    "Selections are held in this session's project. Groups are defined on "
    "the next page; the batch is built on the Batch page."
)
