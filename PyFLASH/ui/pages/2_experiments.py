"""Prepare experiment folders with read-only validation."""
from pathlib import Path
import streamlit as st
from PyFLASH.ui.controls import fold, widget
from PyFLASH.ui import dialogs, services
from PyFLASH.ui.project_io import Project

st.title("Folders")
project = st.session_state.get("project") or Project()
st.session_state["project"] = project
if "_picked_root" in st.session_state:
    st.session_state["ui_folder_root"] = st.session_state.pop("_picked_root")
a, b = st.columns([5, 1], gap="small")
root = widget(a, 'text_input', "Experiment root", value=project.batch_path, key="ui_folder_root", help="The parent folder containing your FLASH experiments. Processing writes results here.")
if widget(b, 'button', "Browse", icon=":material/folder_open:", help="Choose the parent folder on this computer.", key='_control_event_2_experiments_001'):
    picked = dialogs.pick_directory(initial=root or None)
    if picked:
        st.session_state["_picked_root"] = picked
        st.rerun()
mode = widget(st, 'radio', "Choose experiments", ["Discover folders", "Name folders manually"], index=1 if project.experiments else 0,
                horizontal=True, key="ui_folder_mode", help="Discovery validates immediate subfolders. Manual selection uses the table below.")
records, mapping = [], {}
if mode == "Discover folders":
    if root and Path(root).is_dir():
        with st.spinner("Checking experiment folders…"):
            records = services.discover_experiments(root)
    elif root:
        st.error("The experiment root does not exist.")
else:
    edited = widget(st, 'data_editor', [{"name": n, "path": p} for n, p in project.experiments.items()] or [{"name": "", "path": ""}],
                            num_rows="dynamic", use_container_width=True, key="ui_folder_entries",
                            column_config={"name": st.column_config.TextColumn("Experiment", help="A unique experiment name."),
                                           "path": st.column_config.TextColumn("Folder", help="The FLASH experiment folder.")})
    for row in edited:
        if row.get("path"):
            name = row.get("name") or Path(row["path"]).name
            mapping[name] = row["path"]
            records.append(dict(services.validate_experiment_folder(row["path"]), name=name))
if records:
    st.subheader("Folder checks")
    st.dataframe([{"Experiment": r["name"], "Status": "Ready" if r["valid"] else "Needs attention",
                   "Images": "Available" if r["has_images"] else "Not found", "Reason": r["reason"]} for r in records],
                 use_container_width=True, hide_index=True)
    with fold('folders.layout'):
        st.json(records)
elif root:
    st.info("No experiment folders were found.")

with fold('folders.processing'):
    cache = widget(st, 'text_input', "Analysis cache folder", value=project.pickle_path, key="ui_folder_cache", help="Optional location for saved analyses that avoid processing again.")
    threshold = widget(st, 'number_input', "Object threshold", min_value=0, value=int(project.threshold), key="ui_folder_threshold", help="Passed unchanged to the package's experiment processing.")
    images = widget(st, 'toggle', "Import microscopy images", value=project.import_images, key="ui_folder_images", help="Leave off for a measurement-only analysis.")

ready = bool(root) and any(r["valid"] for r in records) and all(r["valid"] for r in records if mode == "Name folders manually")
if widget(st, 'button', "Use these folders", type="primary", icon=":material/check:", disabled=not ready, key='_control_event_2_experiments_002'):
    project.batch_path, project.pickle_path = root, cache
    project.threshold, project.import_images = int(threshold), bool(images)
    project.experiments = mapping
    project.experiment_paths = [r["path"] for r in records if r["valid"]]
    st.switch_page(str(Path(__file__).with_name("3_conditions.py")))
