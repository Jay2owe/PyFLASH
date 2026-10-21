"""Damaged recovery records must not prevent opening the actual interface."""
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
from PyFLASH.ui import workspace, jobs


@pytest.mark.parametrize('error',[ValueError('Unsupported project recovery identity.'),
                                 PermissionError('Saved workspace cannot be read.')])
def test_damaged_recovery_keeps_navigation_available(monkeypatch,error):
    def fail():
        raise error
    monkeypatch.setattr(workspace,'recovery_path',fail)
    app = AppTest.from_file(str(Path('PyFLASH/ui/app.py').resolve())).run(timeout=30)
    assert not app.exception
    assert any('Recovery needs attention' in item.value for item in app.warning)
    assert any('Saved runs' in item.value for item in app.warning)


def test_damaged_completed_result_preserves_previous_result(monkeypatch,tmp_path):
    monkeypatch.setattr(workspace,'recovery_path',lambda:tmp_path/'workspace.json')
    monkeypatch.setattr(jobs,'latest_job',lambda:{'status':'succeeded','id':'0'*32})
    def fail(*args):
        raise ValueError('Damaged completed result')
    monkeypatch.setattr(jobs,'completed_result',fail)
    # The status display is independent; this test isolates result admission.
    monkeypatch.setattr('PyFLASH.ui.job_status.show_status',lambda:None)
    app = AppTest.from_file(str(Path('PyFLASH/ui/app.py').resolve()))
    app.session_state['_ui_dataset_token']='current-source'
    app.session_state['ui_previous_result']={'value':123}
    app.run(timeout=30)
    assert not app.exception
    assert app.session_state['ui_previous_result']=={'value':123}
    assert 'Damaged completed result' in app.session_state['ui_job_error']
