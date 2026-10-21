"""One dependency check and repair control for every feature entry point."""
from PyFLASH.ui.controls import widget
from PyFLASH.dependencies import check


def render(group='core'):
    import streamlit as st
    from PyFLASH.ui import jobs
    missing = [entry for entry in check(group) if not entry['compatible']]
    for entry in missing:
        st.warning(f"{entry['package']} needs {entry['specifier'] or 'installation'}; "
                   f"installed: {entry['version'] or 'missing'}.")
        if widget(st, 'button', f"Install {entry['package']}", icon=':material/build:',
                     key=f"_dependency_repair_{group}_{entry['package']}",
                     help='Install this declared requirement in the running Python environment.'):
            try:
                jobs.start_dependency_repair(entry['package'],
                    dataset_token=st.session_state['_ui_dataset_token'])
                st.rerun()
            except jobs.JobBusyError as exc:
                st.info(str(exc))
    return not missing
