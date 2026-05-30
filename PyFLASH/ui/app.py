"""PyFLASH UI — Streamlit entry point (router + landing page).

Run with::

    streamlit run app.py
    # or, once installed with the [ui] extra:
    pyflash-ui

This is the only place (besides ``pages/``) where ``streamlit`` is imported.
The adapter layer in ``services.py`` stays Streamlit-free.

For now this is a minimal shell: a sidebar router and a landing page showing
the loaded-project status from ``st.session_state`` (empty until later stages
populate it). Real pages are added in stages 02–08.
"""

import streamlit as st

from PyFLASH.ui import services


def _init_session_state() -> None:
    """Seed the keys later stages rely on, without overwriting existing values."""
    st.session_state.setdefault("project", None)  # UI project (paths/conditions)
    st.session_state.setdefault("batch", None)     # in-memory Batch/Experiment
    st.session_state.setdefault("pickle_path", None)


def _render_landing() -> None:
    st.title("PyFLASH UI")
    st.caption(
        "A point-and-click wrapper around the PyFLASH-analysis "
        "immunofluorescence pipeline."
    )

    project = st.session_state.get("project")
    batch = st.session_state.get("batch")

    st.subheader("Project status")
    if project is None and batch is None:
        st.info(
            "No project loaded yet. Use the pages in the sidebar to open an "
            "existing analysis (.pkl) or start a new batch."
        )
    else:
        if batch is not None:
            st.success(f"Loaded object: {type(batch).__name__}")
        if project is not None:
            st.success(f"Active project: {getattr(project, 'name', '(unnamed)')}")

    with st.expander("Environment / package check"):
        try:
            info = services.package_info()
            st.json(info)
        except Exception as exc:  # pragma: no cover - defensive UI guard
            st.error(f"Could not import core PyFLASH: {exc}")


def main() -> None:
    st.set_page_config(page_title="PyFLASH UI", layout="wide")
    _init_session_state()

    with st.sidebar:
        st.header("PyFLASH")
        st.caption("Pages appear here as the UI is built out.")

    _render_landing()


if __name__ == "__main__":
    main()
else:
    # Streamlit executes the script top-to-bottom on every rerun, so render
    # the landing page on import as well as under ``__main__``.
    main()
