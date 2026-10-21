"""One picture-first home for registered plotting and pipeline workflows."""
import streamlit as st
from PyFLASH.ui.controls import fold, widget
from PyFLASH.ui import function_cards, function_contracts as fc, function_editor, function_workbench, function_workflows as flow
from PyFLASH.ui.workflow import page_heading

@fc.catalogue_snapshot()
def _render():
    st.title(page_heading("functions"))
    contracts = fc.catalogue_contracts()
    flow.checked_homes()
    if st.session_state.get("ui_functions_task", "All") not in {"All", *(c.task for c in contracts)}:
        st.session_state["ui_functions_task"] = "All"
    st.session_state.pop("ui_functions_access", None)
    keys = {c.entry.key for c in contracts}
    if st.session_state.get("ui_function_selection") not in keys:
        st.session_state["ui_function_selection"] = "action:" + st.session_state.get("ui_fig_type", "mean_bars")
        if st.session_state["ui_function_selection"] not in keys:
            st.session_state["ui_function_selection"] = contracts[0].entry.key

    st.session_state.pop("ui_functions_page", None)
    st.session_state.pop("ui_functions_filters", None)

    left, right = st.columns([1, 4.8], gap="small")
    with left:
        st.markdown('<span id="function-list"></span>', unsafe_allow_html=True)
        st.markdown('**Choose a picture**')
        @st.fragment
        def inventory():
            widget(st, 'text_input', "Find a plot or pipeline", key="ui_functions_search", help="Search all plot variants and pipelines by picture, purpose or exact function name.")
            task = widget(st, 'selectbox', "Task", ["All"] + sorted({c.task for c in contracts}), key="ui_functions_task", help="Group functions by the work they do.")
        inventory()
        query = st.session_state.get("ui_functions_search", "")
        task = st.session_state.get("ui_functions_task", "All")
        access = "All"
        matches = fc.search(contracts, query, task=task, access=access)
        choices={home.key:'action:'+st.session_state.get('ui_workflow_variant_'+home.key,home.actions[0]) for home in flow.HOMES}
        def choose_picture(item, operation):
            st.session_state['ui_function_selection'] = item.key
        with st.container(height=700, border=False, key="function_catalogue"):
            event = function_cards.render(matches, selected=st.session_state["ui_function_selection"],
                                          all_items=contracts, query=query, task=task, access=access, guided=True, choices=choices,
                                          on_select=choose_picture)
            selected = function_cards.selection([c.entry for c in contracts], event)
            if selected and selected[0].key != st.session_state["ui_function_selection"]:
                st.session_state["ui_function_selection"] = selected[0].key
        with fold('functions.catalogue'):
            st.caption("Registered plotting functions and analysis pipelines. Export tools live in Export; the house aesthetic and supporting package functions live in Workspace.")
            widget(st, 'download_button', "Download input and execution coverage", fc.coverage_document("functions"), "function-coverage.json", "application/json", key='_control_event_9_functions_001')
    with right:
        st.markdown('<span id="function-editor"></span>', unsafe_allow_html=True)
        contract=fc.find(st.session_state['ui_function_selection'])
        home=flow.home(contract.entry.action)
        variant_key='ui_workflow_variant_'+home.key
        st.session_state[variant_key]=contract.entry.action
        def changed_variant():
            st.session_state['ui_function_selection']='action:'+st.session_state[variant_key]
        if len(home.actions)>1:
            titles = {action: flow.title(fc.find(action)) for action in home.actions}
            widget(st,'selectbox','Plot type',home.actions,key=variant_key,on_change=changed_variant,
                   format_func=titles.__getitem__,help='Named variants share this result area. Changing the type starts no computation.')
        function_editor.render(contract)
        function_editor.saved_runs()
        function_workbench.saved_specification()


@st.fragment
def render():
    """Keep form edits local; durable drafts still save after every interaction."""
    try:
        _render()
    finally:
        if st.session_state.get('_workspace_initialised'):
            from PyFLASH.ui import workspace
            try:
                workspace.checkpoint_session(st.session_state)
            except (OSError, ValueError) as exc:
                st.session_state['ui_recovery_error'] = str(exc)
                st.error(f'Could not save workspace preferences: {exc}')


render()
