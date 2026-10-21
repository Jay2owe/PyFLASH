"""Supporting package tools stay with their workflow, outside the plot list."""
from PyFLASH.ui import function_contracts as fc
from PyFLASH.ui.controls import fold, widget


def render(home, title):
    import streamlit as st
    from PyFLASH.ui import function_workbench

    entries = fc.catalogue_contracts(home)
    by_key = {c.entry.key: c for c in entries}
    key = f"ui_{home}_function_selection"
    with fold("tools."+home):
        if st.session_state.get(key) not in by_key:
            st.session_state.pop(key, None)
        selected = widget(st, 'selectbox', "Package function", list(by_key), index=None, key=key,
                                format_func=lambda k: by_key[k].entry.name,
                                placeholder="Find a package function",
                                help="Supporting functions and their original Python reference. Available browser adapters open here.")
        if selected:
            function_workbench.render(by_key[selected])
