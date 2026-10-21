"""Shared workflow frame with a separate recovery copy of UI preferences."""
from pathlib import Path
import json
import sys
import streamlit as st
from PyFLASH.ui.streamlit_compat import install_fast_repl_detection

install_fast_repl_detection()


def _opening_plan():
    """Read recovery once and begin independent input verification."""
    from PyFLASH.ui import workspace
    saved = workspace.read_recovery(workspace.recovery_path())
    source = saved.get("source") or {"kind": "demo", "path": str(workspace.DEMO_PATH)}
    if "--demo" in sys.argv:
        source = {"kind": "demo", "path": str(workspace.DEMO_PATH)}
    if source["kind"] == "demo":
        source["path"] = str(workspace.DEMO_PATH)
    else:
        source["path"] = str(Path(source["path"]).resolve())
    identity = None
    prepared = None
    if Path(source['path']).stat().st_size >= 8*1024**2:
        from PyFLASH.ui.preparation import prepare_source_version, prepare_initial_pickle
        if source['kind'] == 'pickle':
            prepared = prepare_initial_pickle(Path(source['path']))
        if prepared is None:
            identity = prepare_source_version(Path(source['path']))
    return saved, source, identity, prepared


def _init_session_state(prepared_services=None, opening=None):
    if st.session_state.get("_workspace_initialised"):
        return
    st.session_state["_workspace_initialised"] = True
    st.session_state.setdefault("project", None)
    st.session_state.setdefault("batch", None)
    st.session_state.setdefault("pickle_path", None)
    try:
        from PyFLASH.ui import workspace
        from PyFLASH.ui.performance_trace import record, start
        stage = start()
        if prepared_services is not None:
            prepared_services.result()
            record("wait_for_services_import", stage)
        if isinstance(opening, Exception):
            raise opening
        saved, source, identity, prepared = _opening_plan() if opening is None else opening
        # Function drafts are durable; transient widget values (including
        # button triggers and table edit offsets) must never be restored.
        st.session_state.update({key: value for key, value in saved.get("preferences", {}).items()
                                 if not key.startswith("ui_fn_") or key.endswith("_result")})
        if saved.get("layout_version", 0) < 3 and st.session_state.get("ui_explore_height", 850) == 850:
            st.session_state.pop("ui_explore_height", None)
        if saved.get("project"):
            from PyFLASH.ui.project_io import Project
            st.session_state["project"] = Project.from_dict(saved["project"])
        with st.spinner("Opening measurements…"):
            from PyFLASH.ui.loading import open_source, opening_charts
            with opening_charts():
                stage = start()
                captured = prepared.result() if prepared is not None else None
                if prepared is not None:
                    record("wait_for_prepared_pickle", stage)
                captured_args = {} if captured is None else {'_prepared': captured}
                stage = start()
                st.session_state['batch'] = open_source(source,
                    initial_identity={'sha256': captured.sha256} if captured is not None else
                    identity.result() if identity is not None else None, **captured_args)
                record("open_source", stage)
            if source["kind"] == "pickle":
                st.session_state["pickle_path"] = source["path"]
        st.session_state["ui_source"] = source
        workspace.restore_representative_edit(st.session_state)
    except Exception as exc:
        st.session_state["ui_recovery_error"] = str(exc)


def _sidebar():
    from PyFLASH.ui.controls import fold, widget
    from PyFLASH.ui import services
    from PyFLASH.ui.workflow import HELP, STAGES
    from PyFLASH.ui import workspace
    with st.sidebar:
        st.markdown("**PyFLASH**")
        columns = st.columns(2, gap="small")
        for index, stage in enumerate(STAGES):
            with columns[index % 2]:
                st.page_link(str(Path(__file__).parent / "pages" / stage.file),
                             label=stage.label, icon=f":material/{stage.icon}:", help=stage.help)
        batch = st.session_state.get("batch")
        if batch is not None:
            st.markdown(f"**{getattr(batch, 'name', 'Analysis')}**")
            st.caption("Simulated data · 12 subjects" if (st.session_state.get("ui_source") or {}).get("kind") == "demo" else "Loaded analysis")
            bases = services.roi_bases(batch)
            if st.session_state.get("ui_region") not in bases:
                st.session_state["ui_region"] = bases[0]
            widget(st, 'selectbox', "Region", bases, key="ui_region", help=HELP["region"])
        help_fold = fold('app.help')
        if help_fold.open:
            with help_fold:
                for stage in STAGES:
                    st.markdown(f"**{stage.label}** — {stage.help}")
                try:
                    st.caption(f"Recovery copy: {workspace.recovery_path()}")
                except (OSError,ValueError) as exc:
                    st.session_state['ui_recovery_error'] = str(exc)
        if st.session_state.get("ui_recovery_error"):
            st.warning(f"Recovery needs attention: {st.session_state['ui_recovery_error']}")
        if st.session_state.get('ui_job_error'):
            st.warning('Saved runs could not be restored: '+st.session_state['ui_job_error'])


def _checkpoint():
    try:
        from PyFLASH.ui import workspace
        workspace.checkpoint_session(st.session_state)
    except (OSError,ValueError) as exc:
        st.session_state["ui_recovery_error"] = str(exc)
        st.sidebar.error(f"Could not save workspace preferences: {exc}")


def main():
    from PyFLASH.ui.performance_trace import record, start
    stage = start()
    from PyFLASH.ui.preparation import prepare_services
    prepared_services = prepare_services()
    record("schedule_startup_import", stage)
    opening = None
    if not st.session_state.get('_workspace_initialised'):
        stage = start()
        try:
            opening = _opening_plan()
        except Exception as exc:
            opening = exc
        record("schedule_source_preparation", stage)
    stage = start()
    from PyFLASH.ui.theme import CSS
    from PyFLASH.ui.controls import install_native_control_help
    from PyFLASH.ui.workflow import STAGES
    record("import_initial_ui_modules", stage)
    st.set_page_config(page_title="PyFLASH", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    install_native_control_help(st)
    import uuid
    st.session_state.setdefault("_ui_dataset_token", uuid.uuid4().hex)
    stage = start()
    _init_session_state(prepared_services, opening)
    record("initialize_session_data", stage)
    from PyFLASH.ui.job_status import consume_completed
    consume_completed()
    # Detach saved keys from widget cleanup when moving between pages.
    for key in list(st.session_state):
        if key.startswith(("ui_fn_", "ui_functions_")):
            continue
        if key.startswith(("ui_", "qp_", "single_", "cross1_", "cross2_", "cross_cmp_")):
            st.session_state[key] = st.session_state[key]
    pages = {}
    for stage in STAGES:
        pages.setdefault(stage.section, []).append(st.Page(
            Path(__file__).parent / "pages" / stage.file,
            title=stage.label, icon=f":material/{stage.icon}:",
            url_path=stage.key, default=stage.key == "explore"))
    page = st.navigation(pages, position="hidden")
    stage = start()
    _sidebar()
    record("render_sidebar", stage)
    try:
        stage = start()
        page.run()
        record("render_active_page", stage, page=getattr(page, "url_path", None))
        # Register the periodic status fragment after the destination page is
        # drawn. Navigation must finish restoring its views before polling can
        # schedule a fragment-only rerun.
        from PyFLASH.ui.job_status import show_status
        with st.sidebar:
            show_status()
    finally:
        stage = start()
        _checkpoint()
        record("save_session_recovery", stage)
        if __import__('os').environ.get('PYFLASH_AIIFY_WORKSPACE'):
            from PyFLASH.ui.ai_assistant import publish
            try:
                with st.sidebar:
                    publish(st.session_state)
            except (OSError, ValueError) as exc:
                st.sidebar.warning('Assistant state could not be updated: '+str(exc))


main()
