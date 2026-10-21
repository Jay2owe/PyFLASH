"""Small polled status panel; processing never runs on the script thread."""
from pathlib import Path
import streamlit as st
from PyFLASH.ui.controls import fold, widget
from PyFLASH.ui import jobs, workspace


def download_script(result, namespace):
    """Keep the exact script attached to each result, including older results."""
    if result and result.get('script'):
        widget(st, 'download_button', 'Download result script', result['script'],
               'replay.py', 'text/x-python', key='result_script_'+namespace,
               help='Recreates this result from verified inputs in a new output folder.')


def submit(kind, parameters, name, target_key):
    """Snapshot small UI settings and edits; never copy the loaded batch."""
    from PyFLASH.ui import services
    selections = services.get_representative_selections(st.session_state.get("batch"))
    representatives = workspace.selection_snapshot(selections)
    source = dict(st.session_state.get("ui_source") or {})
    version = getattr(st.session_state.get("batch"), "_ui_source_version", None)
    if version is not None:
        if workspace.source_version(source["path"]) != version:
            raise ValueError("The source file changed after it was opened. Reopen it in Workspace before running this operation.")
        source["version"] = version
    jobs.start_operation(kind, source, parameters, name=name,
        dataset_token=st.session_state["_ui_dataset_token"], target_key=target_key,
        representatives=representatives)
    st.rerun()


def consume_completed():
    try:
        state = jobs.latest_job()
    except (OSError,ValueError,KeyError,TypeError) as exc:
        st.session_state['ui_job_error'] = str(exc)
        return
    st.session_state.pop('ui_job_error',None)
    if not state or state["status"] != "succeeded":
        return
    consumed = st.session_state.setdefault("_ui_consumed_jobs", set())
    if state["id"] in consumed:
        return
    try:
        result = jobs.completed_result(state, st.session_state["_ui_dataset_token"])
    except (OSError,ValueError,KeyError,TypeError) as exc:
        st.session_state['ui_job_error'] = str(exc)
        return
    if result is None:
        return
    key, value = result
    if key == "ui_export_log":
        st.session_state['ui_export_result'] = value
        value = value["log"]
    if key == "ui_saved_analysis_result":
        st.session_state["pickle_path"] = value["path"]
        st.session_state["ui_source"] = {"kind": "pickle", "path": value["path"]}
        st.session_state["batch"]._state_path = value["path"]
        st.session_state["batch"]._ui_source_version = workspace.source_version(value["path"])
    st.session_state[key] = value
    if key.startswith("ui_fn_") and key.endswith("_result"):
        history = st.session_state.setdefault("ui_function_results", {})
        history[value["type"]] = value
    consumed.add(state["id"])


def show_status():
    try:
        state = jobs.latest_job()
    except (OSError,ValueError,KeyError,TypeError) as exc:
        st.session_state['ui_job_error'] = str(exc)
        st.warning('Saved runs could not be restored: '+str(exc))
        state = None
    if state is None:
        return
    job_id = state["id"]

    @st.fragment(run_every=1 if state["status"] in jobs.ACTIVE_STATES else None)
    def status_panel():
        try:
            current = jobs.read_job(job_id)
        except (OSError,ValueError,KeyError,TypeError) as exc:
            st.warning('Saved runs could not be restored: '+str(exc))
            return
        status = current["status"]
        if status in jobs.ACTIVE_STATES:
            st.info(f"Running: {current['name']}… You can keep exploring.")
            if current['kind'] == 'sweep':
                import json
                directory = jobs._job_path(jobs.jobs_root(), job_id)
                progress = directory / 'grid-progress.json'
                if progress.is_file():
                    grid = json.loads(progress.read_text(encoding='utf-8'))
                    st.progress(len(grid['items']) / (len(grid['items']) + len(grid['pending'])),
                                text=f"{len(grid['items'])} complete · {len(grid['pending'])} remaining")
                    from PyFLASH.ui.sweeps import show_grid
                    cells = [workspace.read_operation_state(file)
                             for file in sorted(directory.glob('cell-*/result.json'))]
                    if cells:
                        show_grid(st, {'cells':cells, 'choices':grid['choices']}, namespace=job_id, promote=False)
                if widget(st, 'button', 'Cancel after this cell', key='cancel_grid_'+job_id,
                          help='Keeps every completed cell available for resume.'):
                    jobs.cancel_job(job_id)
        elif status == "succeeded":
            st.success(f"{current['name']} is ready.")
            recipe = jobs._job_path(jobs.jobs_root(), job_id) / 'equivalent.py'
            if recipe.is_file():
                widget(st, 'download_button', 'Download run script', recipe.read_text(encoding='utf-8'),
                       'replay.py', 'text/x-python', key='job_replay_'+job_id,
                       help='Recreates this result from verified inputs in a new output folder.')
            if current.get("kind", "processing") == "processing" and widget(st, 'button', "Open completed analysis", icon=":material/query_stats:", key=f"open_job_{job_id}"):
                try:
                    from PyFLASH.ui.loading import open_source
                    source = {"kind": "pickle", "path": current["result_path"]}
                    batch = open_source(source)
                    workspace.activate_dataset(st.session_state, batch,
                        source)
                    st.switch_page(str(Path(__file__).parent / "pages/5_summary.py"))
                except Exception as exc:
                    st.error(f"Could not open the completed analysis: {exc}")
        else:
            st.error(f"Processing failed: {current.get('error', 'See the processing log.')}")
            recipe = jobs._job_path(jobs.jobs_root(),job_id)/'equivalent.py'
            if recipe.is_file():
                widget(st,'download_button','Download failed run script',recipe.read_text(encoding='utf-8'),
                       'replay_failed.py','text/x-python',key='job_replay_failed_'+job_id,
                       help='Replays these recorded settings from verified inputs in a new folder.')
            if current.get('receipt_error'):
                st.error('Run evidence could not be saved: '+current['receipt_error'])
        with fold('jobs.log', namespace=job_id+":"):
            st.code(jobs.log_tail(job_id) or "Starting the analysis…", language="text")
        if status not in jobs.ACTIVE_STATES and state["status"] in jobs.ACTIVE_STATES:
            # Stop the periodic fragment after completion and refresh admission controls.
            st.rerun()

    status_panel()
