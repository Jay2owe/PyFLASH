"""Each older export retains its own downloadable script after another job runs."""
from types import SimpleNamespace
import pandas as pd
from streamlit.testing.v1 import AppTest
from PyFLASH.ui import job_status


def test_three_older_export_scripts_remain_available(tmp_path,monkeypatch):
    csv = tmp_path/'summary.csv'
    csv.write_text('AnimalName,Signal\na,1.25\n',encoding='utf-8')
    batch = SimpleNamespace(summary=pd.DataFrame({'AnimalName':['a'],'Signal':[1.25]}),
        name='fixture',filePath=str(tmp_path),export_all_excel=lambda **kwargs:None)
    downloads = {}
    original = job_status.widget
    def observed(target,kind,*args,**kwargs):
        if kind=='download_button':
            downloads[kwargs['key']] = args[1]
        return original(target,kind,*args,**kwargs)
    monkeypatch.setattr(job_status,'widget',observed)
    app = AppTest.from_file('PyFLASH/ui/pages/8_export.py',default_timeout=20)
    app.session_state['batch'] = batch
    app.session_state['ui_csv_result'] = {'region':None,'path':str(csv),'script':'# original CSV recipe'}
    app.session_state['ui_export_log'] = 'Original workbook run finished'
    app.session_state['ui_export_result'] = {'script':'# original workbook recipe'}
    app.session_state['ui_saved_analysis_result'] = {'path':str(tmp_path/'saved.pkl'),'script':'# original save recipe'}
    app.run()
    assert not app.exception,[e.message for e in app.exception]
    assert len([e for e in app.get('download_button') if e.proto.label=='Download result script'])==3
    assert downloads=={'result_script_export_csv':'# original CSV recipe',
        'result_script_export_workbooks':'# original workbook recipe','result_script_export_save':'# original save recipe'}
