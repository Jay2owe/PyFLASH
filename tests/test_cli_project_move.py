"""CLI records and unchanged scripts follow an actually moved project folder."""
import json
from pathlib import Path
import subprocess
import pytest
from PyFLASH import control
from PyFLASH.ui import workspace
from reproducibility.run import python_command


@pytest.mark.parametrize('action',['mean_bars','PyFLASH.ui.services.export_summary_csv',
                                  'PyFLASH.ui.workspace.load_table'])
def test_recorded_internal_paths_and_unchanged_script_survive_project_move(tmp_path,monkeypatch,capsys,action):
    project = tmp_path/'original-project'
    moved = tmp_path/'moved-project'
    project.mkdir()
    monkeypatch.chdir(project)
    source = project/'subjects.csv'
    source.write_bytes(workspace.DEMO_PATH.read_bytes())
    output = project/'result'
    if action=='mean_bars':
        parameters = {'data_cols':['Signal_MeanIntensity'],'save':False,'save_normality':False}
    elif action.endswith('load_table'):
        parameters = {'path':str(source)}
    else:
        parameters = {'filename':str(project/'selected.csv'),'groups':['Control'],
                      'columns':['AnimalName','Signal_MeanIntensity']}
    command = ['run',action,'--params',json.dumps(parameters),'--output',str(output)]
    if not action.endswith('load_table'):
        command += ['--input',str(source)]
    assert control.main(command)==0
    answer = json.loads(capsys.readouterr().out.splitlines()[-1])
    script = (output/'equivalent.py').read_bytes()
    record = answer['provenance']
    assert all(not Path(row['path']).is_absolute() for row in record['parameter_inputs'])
    assert all(not Path(row['path']).is_absolute() for row in record['outputs'])
    if record['source']:
        assert record['source']['path']=='subjects.csv'
    monkeypatch.chdir(tmp_path)
    assert project.resolve().is_relative_to(tmp_path.resolve()) and moved.resolve().is_relative_to(tmp_path.resolve())
    project.rename(moved)
    monkeypatch.chdir(moved)
    child = subprocess.run(python_command()+[str(moved/'result/equivalent.py')],cwd=moved,
                           capture_output=True,text=True,encoding='utf-8',timeout=45)
    assert child.returncode==0,child.stderr
    assert (moved/'result/equivalent.py').read_bytes()==script
    reopened = workspace.read_run_record(moved/'result/run.json')['provenance']
    assert all(workspace.content_hash(row['path'])==row['sha256'] for row in reopened['outputs'])
    assert all(workspace.content_hash(row['path'])==row['sha256'] for row in reopened['parameter_inputs'])
    if action.endswith('export_summary_csv'):
        import pandas as pd
        pd.testing.assert_frame_equal(pd.read_csv(moved/'selected.csv'),
                                      pd.read_csv(moved/'replayed-output/selected.csv'),check_exact=True)


def test_old_run_record_migrates_without_rewriting_and_future_version_fails(tmp_path):
    record = {'schema_version':1,'source':None,'outputs':[],
              'parameters':{'scientific_label':'C:/marker/name'}}
    path = tmp_path/'legacy-run.json'
    path.write_text(json.dumps(record))
    before = path.read_bytes()
    reopened = workspace.read_run_record(path)
    assert reopened['schema_version']==workspace.RUN_RECORD_SCHEMA_VERSION
    assert reopened['parameters']==record['parameters']
    assert path.read_bytes()==before
    path.write_text(json.dumps({**record,'schema_version':workspace.RUN_RECORD_SCHEMA_VERSION+1}))
    with pytest.raises(ValueError,match='unsupported version'):
        workspace.read_run_record(path)
