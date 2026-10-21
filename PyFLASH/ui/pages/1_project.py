"""Open actual inputs and manage saved project setup."""
from pathlib import Path
import streamlit as st
from PyFLASH.ui.controls import fold, widget
from PyFLASH.ui import dialogs, services, workspace
from PyFLASH.ui.project_io import Project

st.title("Workspace")


def _activate(batch, source):
    workspace.activate_dataset(st.session_state, batch, source)
    st.switch_page(str(Path(__file__).with_name("5_summary.py")))


open_col, setup_col = st.columns([3, 2], gap="small")
with open_col:
    st.subheader("Open data")
    kind = widget(st, 'radio', "Input", ["Saved analysis", "Subject table"], horizontal=True,
                    help="Saved analysis: processed measurements. Subject table: a CSV file.", key='ui_control_1_project_001')
    if st.session_state.get("_picked_source"):
        st.session_state["ui_open_path"] = st.session_state.pop("_picked_source")
    path = widget(st, 'text_input', "File path", key="ui_open_path", help="A .pkl analysis or .csv subject table on this computer.")
    if widget(st, 'button', "Browse", icon=":material/folder_open:", key='_control_event_1_project_002'):
        picked = dialogs.pick_file([("Analysis or subject table", "*.pkl *.csv")])
        if picked:
            st.session_state["_picked_source"] = picked
            st.rerun()
    group_col, subject_col = "Condition", "AnimalName"
    if kind == "Subject table":
        a, b = st.columns(2)
        group_col = widget(a, 'text_input', "Group column", value="Condition", help="The column defining groups.", key='ui_control_1_project_007')
        subject_col = widget(b, 'text_input', "Subject column", value="AnimalName", help="The column identifying subjects.", key='ui_control_1_project_008')
    if widget(st, 'button', "Open data", type="primary", icon=":material/upload:", disabled=not path.strip(), key='_control_event_1_project_003'):
        try:
            with st.spinner("Opening measurements…"):
                if kind == "Saved analysis":
                    source = {"kind": "pickle", "path": str(Path(path).resolve())}
                else:
                    source = {"kind": "csv", "path": str(Path(path).resolve()), "group_col": group_col, "subject_col": subject_col}
                from PyFLASH.ui.loading import open_source
                batch = open_source(source)
            _activate(batch, source)
        except Exception as exc:
            st.error(f"Could not open data: {exc}")
    if widget(st, 'button', "Use simulated example", icon=":material/science:", help="12 simulated subjects in two groups; no real microscopy images.", key='_control_event_1_project_004'):
        from PyFLASH.ui.loading import open_source
        source = {"kind": "demo", "path": str(workspace.DEMO_PATH)}
        _activate(open_source(source), source)

with setup_col:
    st.subheader("Project setup")
    project = st.session_state.get("project") or Project()
    if "_restored_name" in st.session_state:
        st.session_state["ui_project_name"] = st.session_state.pop("_restored_name")
    project.name = widget(st, 'text_input', "Project name", value=project.name, key="ui_project_name", help="Names the batch created in Process.")
    st.session_state["project"] = project
    st.page_link(str(Path(__file__).with_name("2_experiments.py")), label="Choose experiment folders", icon=":material/folder_copy:")
    uploaded = widget(st, 'file_uploader', "Load project setup", type=["json"], help="Restore folder and group definitions without processing.", key='_control_event_1_project_005')
    if uploaded and widget(st, 'button', "Restore setup", icon=":material/restore:", key='_control_event_1_project_009'):
        try:
            restored = Project.from_json(uploaded.getvalue().decode("utf-8"))
            for key in list(st.session_state):
                if key.startswith(("single_", "cross1_", "cross2_", "cross_cmp_", "ui_group_", "ui_folder_")):
                    del st.session_state[key]
            st.session_state["project"] = restored
            st.session_state["_restored_name"] = restored.name
            st.rerun()
        except Exception as exc:
            st.error(f"Could not restore setup: {exc}")
    widget(st, 'download_button', "Save project setup", project.to_json(), "pyflash-project.json", mime="application/json", icon=":material/download:", key='_control_event_1_project_006')

batch = st.session_state.get("batch")
if batch is not None:
    with fold('workspace.provenance'):
        st.json(services.batch_overview(batch))
        st.json(st.session_state.get("ui_source", {}))

from PyFLASH.ui import appearance, function_tools
appearance.render()
with fold('workspace.dependencies'):
    from PyFLASH.ui import dependency_controls
    dependency_controls.render(None)
function_tools.render("workspace", "Other package functions")
