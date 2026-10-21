"""Existing image navigation opens the canonical function editor."""
from pathlib import Path
import streamlit as st

if st.session_state.pop('ui_image_open_location', False):
    action = 'locations'
else:
    action = 'representative_images' if st.session_state.get('ui_image_mode') == 'Representative images' else 'images'
st.session_state['ui_function_selection'] = 'action:' + action
st.switch_page(str(Path(__file__).with_name('9_functions.py')))