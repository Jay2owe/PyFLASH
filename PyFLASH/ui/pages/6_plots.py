"""Existing figure navigation opens the canonical function editor."""
from pathlib import Path
import streamlit as st

st.session_state['ui_function_selection'] = 'action:' + st.session_state.get('ui_fig_type', 'mean_bars')
st.switch_page(str(Path(__file__).with_name('9_functions.py')))