"""Project page — open an existing analysis (.pkl) and show its overview.

Loads a saved ``Batch``/``Experiment`` via ``services.open_pickle`` (a thin
wrapper over ``serialization.load_state``) and stores it in
``st.session_state["batch"]`` so every later page can reuse it. Read-only: no
data is created or mutated here.

Streamlit is imported here (a page), never in ``services.py``.
"""

import streamlit as st

from PyFLASH.ui import dialogs, services

st.header("Project")
st.caption("Open an existing analysis (.pkl) and inspect what it contains.")

col_path, col_browse = st.columns([4, 1])
path = col_path.text_input(
    "Batch pickle (.pkl)",
    value=st.session_state.get("pickle_path", "") or "",
)
if col_browse.button("Browse…"):
    picked = dialogs.pick_file([("Pickle", "*.pkl"), ("All files", "*.*")])
    if picked:
        path = picked
        st.session_state["pickle_path"] = picked

if st.button("Open", type="primary", disabled=not path):
    try:
        st.session_state["batch"] = services.open_pickle(path)
        st.session_state["pickle_path"] = path
        st.success(f"Loaded {path}")
    except Exception as exc:  # pragma: no cover - defensive UI guard
        st.error(f"Could not load pickle: {exc}")

batch = st.session_state.get("batch")
if batch is not None:
    st.subheader("Overview")
    overview = services.batch_overview(batch)
    st.json(overview)

    state_path = getattr(batch, "_state_path", None)
    if state_path:
        st.caption(f"Loaded from: {state_path}")
    st.info(
        "Paths inside the pickle were rebased on load. If this analysis was "
        "made on another machine, some image/plot features may be limited "
        "until paths resolve (see Config.FALLBACK_USERS)."
    )
    st.caption("Browse the numbers on the Summary page.")
else:
    st.info("No analysis loaded yet. Enter a .pkl path above and press Open.")
