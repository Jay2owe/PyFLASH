"""Compact exports, with availability checks against the loaded object."""
from pathlib import Path
import streamlit as st
from PyFLASH.ui.controls import fold, widget
from PyFLASH.ui import services
from PyFLASH.ui.job_status import submit, download_script

st.title("Export")
batch = st.session_state.get("batch")
if batch is None:
    st.info("Open data in Workspace, or build an analysis in Process.")
    st.stop()

table = services.summary_table(batch, roi_base=st.session_state.get("ui_region"), display=False)
st.subheader("Measurements")
if table is not None:
    if widget(st, 'button', "Prepare region summary", icon=":material/download:", help="Prepares the complete CSV in the background; you can keep exploring.", key='_control_event_8_export_002'):
        try:
            submit("csv", {"region": st.session_state.get("ui_region")}, "Region summary export", "ui_csv_result")
        except Exception as exc:
            st.error(f"Could not prepare the summary: {exc}")
    csv = st.session_state.get("ui_csv_result")
    if csv and csv["region"] == st.session_state.get("ui_region") and Path(csv["path"]).is_file():
        with open(csv["path"], "rb") as stream:
            widget(st, 'download_button', "Download region summary", stream, "summary.csv", "text/csv", icon=":material/download:", key='_control_event_8_export_004')
        download_script(csv, 'export_csv')

st.subheader("Excel workbooks")
if callable(getattr(batch, "export_all_excel", None)):
    workbooks = (("if_summary", "Summary", "IF_Summary"), ("if_extended", "Per-object data", "IF_Extended"), ("behaviour", "Behaviour", "Behavior_Summary"))
    selected, includes, excludes, names = {}, {}, {}, {}
    for column, (key, label, default) in zip(st.columns(3), workbooks):
        selected[key] = widget(column, 'checkbox', label, value=key == "if_summary", key=f"ui_export_{key}", help="Include this workbook in the export.")
    with fold('export.filters'):
        for key, label, default in workbooks:
            st.markdown(f"**{label}**")
            a, b, c = st.columns(3)
            includes[key] = widget(a, 'text_input', "Include matching columns", key=f"ui_export_include_{key}", help="Comma-separated regular expressions. Blank includes all columns.")
            excludes[key] = widget(b, 'text_input', "Exclude matching columns", key=f"ui_export_exclude_{key}", help="Comma-separated regular expressions. Blank excludes nothing.")
            names[key] = widget(c, 'text_input', "File name", value=default, key=f"ui_export_name_{key}", help="The workbook name without its .xlsx extension.")
    target = widget(st, 'text_input', "Workbook destination", value=getattr(batch, "export_path", "") or "", key="ui_export_path", help="Blank uses the analysis export folder.")
    if widget(st, 'button', "Export selected workbooks", type="primary", icon=":material/download:", disabled=not any(selected.values()), key='_control_event_8_export_003'):
        try:
            kwargs = {"save_path": target.strip() or None, **selected}
            for key, _, _ in workbooks:
                for field, values in (("include", includes), ("exclude", excludes)):
                    patterns = [v.strip() for v in values[key].split(",") if v.strip()] or None
                    services.validate_regex(patterns)
                    kwargs[f"{key}_{field}"] = patterns
                kwargs[f"{key}_save_name"] = names[key].strip() or None
            submit("workbooks", kwargs, "Excel workbooks", "ui_export_log")
        except Exception as exc:
            st.error(f"Could not export workbooks: {exc}")
    if st.session_state.get("ui_export_log"):
        download_script(st.session_state.get('ui_export_result'), 'export_workbooks')
        with fold('export.log'):
            st.code(st.session_state["ui_export_log"], language="text")
else:
    st.info("This subject-table analysis supports CSV export. Processed FLASH batches also provide formatted Excel workbooks.")

st.subheader("Save analysis")
state_path = getattr(batch, "_state_path", None)
default = str(state_path or (Path(getattr(batch, "filePath", ".")) / "analysis.pkl"))
filename = widget(st, 'text_input', "Analysis file", value=default, key="ui_save_analysis", help="Save measurements and representative image selections to a .pkl file.")
if widget(st, 'button', "Save analysis", icon=":material/save:", disabled=not filename.strip(), key='_control_event_8_export_001'):
    try:
        submit("save", {"filename": filename}, "Save analysis", "ui_saved_analysis_result")
    except Exception as exc:
        st.error(f"Could not save analysis: {exc}")
if st.session_state.get("ui_saved_analysis_result"):
    st.success(f"Saved analysis: {st.session_state['ui_saved_analysis_result']['path']}")
    download_script(st.session_state['ui_saved_analysis_result'], 'export_save')

from PyFLASH.ui import function_tools
function_tools.render("export", "Export package reference")
