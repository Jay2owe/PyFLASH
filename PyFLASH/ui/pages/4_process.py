"""Deliberate processing with preflight and durable captured output."""
from pathlib import Path
import streamlit as st
from PyFLASH.ui.controls import fold, widget
from PyFLASH.ui import services, jobs
from PyFLASH.ui.project_io import Project

st.title("Process")
project = st.session_state.get("project") or Project()
st.session_state["project"] = project
problems = []
if not project.batch_path:
    problems.append("Choose experiment folders.")
if not project.conditions:
    problems.append("Define the experimental groups.")
conditions = None
if project.conditions:
    try:
        conditions = services.build_conditions(project.conditions)
    except Exception as exc:
        problems.append(str(exc))
if problems:
    st.info("Processing setup needs attention: " + " ".join(problems))
else:
    st.success("Folders and groups are ready to process.")

with fold('process.inputs'):
    st.markdown(f"**{project.name}**")
    st.text(project.batch_path or "No folder selected")
    if conditions:
        st.dataframe(services.preview_conditions(conditions)["conditions"], use_container_width=True, hide_index=True)
    st.caption(f"Object threshold: {project.threshold} · Microscopy images: {'included' if project.import_images else 'excluded'}")
with fold('process.advanced'):
    rerun = widget(st, 'toggle', "Reprocess cached analysis", False, key="ui_process_rerun", help="Ignore an existing saved analysis and process the experiment files again.")
    reimport = widget(st, 'toggle', "Reload microscopy images", False, disabled=not rerun, key="ui_process_reimport", help="Reload images while reprocessing.")

active = jobs.latest_job()
busy = active is not None and active["status"] in jobs.ACTIVE_STATES
if widget(st, 'button', "Process experiments", type="primary", icon=":material/play_arrow:", disabled=bool(problems) or busy, key='_control_event_4_process_001'):
    try:
        jobs.start_processing(project.to_dict(), rerun=rerun, reimport_images=reimport)
        st.rerun()
    except Exception as exc:
        st.error(f"Processing failed: {exc}")

if st.session_state.get("batch") is not None:
    st.page_link(str(Path(__file__).with_name("5_summary.py")), label="Inspect measurements", icon=":material/query_stats:")
