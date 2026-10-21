"""The closed detail panel does no table work; opening retains all shown data."""
from pathlib import Path
import pytest


@pytest.mark.slow
def test_measurement_table_loads_on_open_and_keeps_linked_charts(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    page = Path(__file__).resolve().parents[1]/'PyFLASH/ui/pages/5_summary.py'
    app = AppTest.from_string(
        "import streamlit as st\n"
        "from PyFLASH.ui import workspace\n"
        "if 'batch' not in st.session_state:\n"
        "    st.session_state['batch']=workspace.load_table(workspace.DEMO_PATH,demo=True)\n"
        "import runpy\n"
        f"runpy.run_path({str(page)!r})\n",default_timeout=20)
    app.run()
    assert not app.exception
    assert not app.dataframe
    assert len(app.get('vega_lite_chart')) == 2
    before = [element.proto.spec for element in app.get('vega_lite_chart')]
    app.session_state['ui_fold_explore.measurements'] = True
    app.run()
    assert not app.exception
    assert len(app.dataframe) == 1
    assert len(app.dataframe[0].value) == 12
    assert [element.proto.spec for element in app.get('vega_lite_chart')] == before
    assert any(button.label == 'Prepare shown table' for button in app.button)
    app.session_state['ui_fold_explore.measurements'] = False
    app.run()
    assert not app.exception and not app.dataframe
