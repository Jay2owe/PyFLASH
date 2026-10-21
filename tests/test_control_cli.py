"""The installable CLI reads browser registries and rejects calls before writes."""
import json
import pytest
from pathlib import Path
from PyFLASH import actions, control, spec
from PyFLASH.ui import function_contracts


def test_cli_and_browser_have_one_helper_registry():
    assert function_contracts.PUBLIC is actions.HELPER_ACTIONS
    entries = control.describe()
    assert {r['action'] for r in entries} == set(spec.PLOT_REGISTRY)|set(actions.ACTION_REGISTRY)


@pytest.mark.slow
def test_top_level_queue_has_a_receipt_and_unchanged_script_replays(tmp_path,capsys):
    import subprocess
    from reproducibility.run import python_command
    from PyFLASH.ui import workspace
    source = tmp_path/'subjects.csv'
    source.write_bytes(workspace.DEMO_PATH.read_bytes())
    recipe = tmp_path/'recipe.json'
    # Exercise the actual public plot; no figure file is needed for this queue/replay contract.
    recipe.write_text(json.dumps({'plots':[{'type':'mean_bars','data_cols':['Signal_MeanIntensity'],
                                          'save':False,'save_normality':False}]}))
    progress, output = tmp_path/'progress.json',tmp_path/'receipt'
    command = ['queue','--input',str(source),'--spec',str(recipe),'--progress',str(progress),'--output',str(output)]
    assert control.main(command) == 0
    answer = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert answer['ok'] and answer['equivalent_script']
    assert (output/'run.json').is_file()
    assert {row['parameter'] for row in answer['provenance']['parameter_inputs']} == {'source','path'}
    assert all(workspace.content_hash(row['path']) == row['sha256'] for row in answer['provenance']['outputs'])
    before = progress.read_bytes()
    fresh = tmp_path/'fresh'
    fresh.mkdir()
    result = subprocess.run(python_command()+[str(output/'equivalent.py')],cwd=fresh,
                            capture_output=True,text=True,encoding='utf-8',timeout=40)
    assert result.returncode == 0,result.stderr
    replayed = json.loads((fresh/'replayed-output/progress.json').read_text())
    assert replayed['items'][0]['status'] == 'done'
    assert progress.read_bytes() == before
    # Resume without requesting a new receipt path uses an owned attempt folder.
    assert control.main(command[:-2]) == 0
    resumed = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert resumed['result']['successes'] == [0]
    assert len(json.loads(progress.read_text())['items'][0]['attempts']) == 1


def test_unknown_plot_parameter_fails_before_output_creation(tmp_path,capsys):
    output = tmp_path/'untouched'
    assert control.main(['run','mean_bars','--params','{"pionts":false}','--output',str(output)]) == 1
    response = json.loads(capsys.readouterr().out)
    assert 'Unknown parameters: pionts' in response['error'] and not output.exists()


def test_helper_run_retains_equivalent_script_and_receipt(tmp_path,capsys):
    output = tmp_path/'helper'
    assert control.main(['run','PyFLASH.stats.bonferroni_correction',
                         '--params','{"p_value":0.02,"n_tests":3}','--output',str(output)]) == 0
    response = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert response['ok'] and response['result'] == .06
    assert response['provenance']['configuration']['EFFECT_CI_RANDOM_STATE'] == 0
    assert (output/'run.json').is_file() and (output/'equivalent.py').is_file()


@pytest.mark.slow
def test_failed_cli_action_retains_original_error_receipt_and_replay(tmp_path,capsys):
    import subprocess
    from reproducibility.run import python_command
    output = tmp_path/'failed'
    assert control.main(['run','PyFLASH.stats.bonferroni_correction',
                         '--params','{"p_value":0.02,"n_tests":"invalid"}',
                         '--output',str(output)]) == 1
    response = json.loads(capsys.readouterr().out.splitlines()[-1])
    retained = json.loads((output/'run.json').read_text())
    assert retained == response
    assert retained['provenance']['status'] == 'failed'
    assert retained['provenance']['error'] == response['error']
    assert retained['provenance']['code_sha256'] and retained['provenance']['dependencies']
    assert retained['equivalent_script'] == (output/'equivalent.py').read_text(encoding='utf-8')
    before = (output/'run.json').read_bytes()
    fresh = tmp_path/'fresh-failure'
    fresh.mkdir()
    child = subprocess.run(python_command()+[str(output/'equivalent.py')],cwd=fresh,
                           capture_output=True,text=True,encoding='utf-8',timeout=30)
    assert child.returncode != 0 and response['error'] in child.stderr
    assert (output/'run.json').read_bytes() == before
    # A directory already owned by another attempt is never replaced on error.
    assert control.main(['run','PyFLASH.stats.bonferroni_correction',
                         '--params','{"p_value":0.02,"n_tests":3}',
                         '--output',str(output)]) == 1
    capsys.readouterr()
    assert (output/'run.json').read_bytes() == before


def test_failed_cli_capture_keeps_input_identity_before_action_changes_it(tmp_path,capsys,monkeypatch):
    from PyFLASH.ui.workspace import content_hash
    source = tmp_path/'subjects.csv'
    source.write_text('AnimalName,Condition,Signal\na,A,1\nb,B,2\n')
    original = content_hash(source)
    def change_then_fail(*args,**kwargs):
        source.write_text(source.read_text()+'c,A,3\n')
        raise ValueError('controlled failure after input changed')
    monkeypatch.setattr(control,'call_action',change_then_fail)
    output = tmp_path/'changed-input'
    assert control.main(['run','mean_bars','--input',str(source),
                         '--params','{"data_cols":["Signal"]}','--output',str(output)]) == 1
    response = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert response['provenance']['source']['sha256'] == original
    assert original in response['equivalent_script']
    assert content_hash(source) not in response['equivalent_script']


def test_support_file_input_is_hashed_and_unchanged_script_replays(tmp_path,capsys):
    from reproducibility.run import python_command
    import subprocess
    source = tmp_path/'subjects.csv'
    source.write_text('AnimalName,Condition,Signal\na,A,1\nb,B,2\n',encoding='utf-8')
    output = tmp_path/'opened'
    assert control.main(['run','PyFLASH.ui.workspace.load_table',
        '--params',json.dumps({'path':str(source)}),'--output',str(output)]) == 0
    response = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert response['provenance']['parameter_inputs'][0]['path'] == str(source.resolve())
    replay = subprocess.run(python_command()+[str(output/'equivalent.py')],
        capture_output=True,text=True,timeout=30)
    assert replay.returncode == 0, replay.stderr
    source.write_text(source.read_text()+'c,A,3\n')
    rejected = subprocess.run(python_command()+[str(output/'equivalent.py')],
        capture_output=True,text=True,timeout=30)
    assert rejected.returncode != 0 and 'Input content changed' in rejected.stderr


@pytest.mark.slow
def test_cli_source_free_grid_records_outputs_and_replays_in_fresh_directory(tmp_path,capsys):
    import subprocess
    from reproducibility.run import python_command
    output = tmp_path/'grid-run'
    parameters = {'action':'PyFLASH.stats.bonferroni_correction','parameters':{'p_value':.01},
                  'choices':{'n_tests':[2,3]},'progress_path':str(tmp_path/'original-progress.json')}
    assert control.main(['run','PyFLASH.queue.run_action_grid','--params',json.dumps(parameters),
                         '--output',str(output)]) == 0
    response = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert [row['result'] for row in response['result']['results']] == [.02,.03]
    assert response['provenance']['outputs']
    from PyFLASH.ui.workspace import content_hash
    assert all(content_hash(row['path']) == row['sha256'] for row in response['provenance']['outputs'])
    before = (tmp_path/'original-progress.json').read_bytes()
    fresh = tmp_path/'fresh'
    fresh.mkdir()
    child = subprocess.run(python_command()+[str(output/'equivalent.py')],cwd=fresh,
                           capture_output=True,text=True,encoding='utf-8',timeout=40)
    assert child.returncode == 0, child.stderr
    progress = json.loads((fresh/'replayed-output/original-progress.json').read_text())
    assert len(progress['items']) == 2 and not progress['pending'] and not progress['failures']
    assert (tmp_path/'original-progress.json').read_bytes() == before


def test_cli_csv_output_is_hashed_and_replay_retains_exact_subset(tmp_path,capsys):
    import subprocess
    import pandas as pd
    from reproducibility.run import python_command
    from PyFLASH.ui.workspace import content_hash
    source = tmp_path/'subjects.csv'
    source.write_text('AnimalName,Condition,Signal,Other\na,A,1,9\nb,B,2,8\nc,A,3,7\n')
    destination = tmp_path/'selected.csv'
    parameters = {'filename':str(destination),'groups':['A'],'columns':['AnimalName','Signal']}
    output = tmp_path/'run'
    assert control.main(['run','PyFLASH.ui.services.export_summary_csv','--input',str(source),
                         '--params',json.dumps(parameters),'--output',str(output)]) == 0
    response = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert {'path':str(destination.resolve()),'sha256':content_hash(destination)} in response['provenance']['outputs']
    fresh = tmp_path/'fresh'
    fresh.mkdir()
    child = subprocess.run(python_command()+[str(output/'equivalent.py')],cwd=fresh,
                           capture_output=True,text=True,encoding='utf-8',timeout=40)
    assert child.returncode == 0, child.stderr
    pd.testing.assert_frame_equal(pd.read_csv(destination),pd.read_csv(fresh/'replayed-output/selected.csv'),check_exact=True)
    assert pd.read_csv(destination).to_dict('list') == {'AnimalName':['a','c'],'Signal':[1,3]}


def test_cli_describes_same_choices_units_and_labels_as_browser():
    contract = function_contracts.find('mean_bars')
    answer = control.describe('mean_bars')
    fields = {row['name']:row for row in answer['parameters']}
    for field in contract.fields:
        assert fields[field.name]['key'] == field.name
        assert fields[field.name]['label'] == field.label
        assert fields[field.name]['help'] and fields[field.name]['unit']
        if field.choices:
            assert fields[field.name]['choices'] == list(field.choices)
