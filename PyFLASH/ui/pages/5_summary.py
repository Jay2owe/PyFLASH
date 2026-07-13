"""Summary page — browse the loaded batch's summary tables and export CSV.

Reads the ``Batch``/``Experiment`` placed in ``st.session_state["batch"]`` by
the Project page. Lets the user pick an ROI base, toggle human-readable display
labels vs raw column names, optionally filter columns, and download the shown
table as CSV. All table shaping is delegated to ``services`` (Streamlit-free).
"""

import streamlit as st

from PyFLASH.ui import services

st.header("Summary")

batch = st.session_state.get("batch")
if batch is None:
    st.info("No analysis loaded. Open a .pkl on the Project page first.")
    st.stop()

bases = services.roi_bases(batch)

col_roi, col_display = st.columns([2, 2])
roi_base = col_roi.selectbox("ROI base", bases, index=0)
display = col_display.toggle(
    "Display labels",
    value=True,
    help="On: human-readable, unit-labelled headers. Off: raw column names.",
)

with st.expander("Column filter (optional)"):
    st.caption(
        "Keep only columns containing any of these substrings (comma-separated). "
        "Subject and group columns are always kept."
    )
    include_raw = st.text_input("Include columns containing", value="")
    exclude_raw = st.text_input("Exclude columns containing", value="")

column_strings = [s.strip() for s in include_raw.split(",") if s.strip()] or None
exclude = [s.strip() for s in exclude_raw.split(",") if s.strip()] or None

try:
    table = services.summary_table(
        batch,
        roi_base=roi_base,
        display=display,
        column_strings=column_strings,
        exclude=exclude,
    )
except Exception as exc:  # pragma: no cover - defensive UI guard
    st.error(f"Could not build summary table: {exc}")
    st.stop()

if table is None:
    st.warning("This object has no summary table to show.")
    st.stop()

st.caption(f"{table.shape[0]} rows x {table.shape[1]} columns")
st.dataframe(table, use_container_width=True)

csv = table.to_csv(index=False).encode("utf-8")
st.download_button(
    "Download CSV",
    data=csv,
    file_name=f"{getattr(batch, 'name', 'summary')}_{roi_base}.csv",
    mime="text/csv",
)
