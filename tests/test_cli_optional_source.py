"""The CLI honors the owning plot's optional dataset contract."""
import json
import subprocess
from pathlib import Path
import pytest
from PyFLASH import control
from reproducibility.run import python_command


def test_source_free_power_plot_retains_a_replay_of_every_curve_point(tmp_path,capsys):
    output = tmp_path/'power'
    parameters = {'effect_sizes':[.2,.8],'n_range':[2,5],
                  'save':False,'return_data':True}
    assert control.main(['run','power_curve','--params',json.dumps(parameters),
                         '--output',str(output)]) == 0
    response = json.loads(capsys.readouterr().out.splitlines()[-1])
    expected = response['result'][1]['data']
    assert len(expected['data']) == 8
    script = (output/'equivalent.py').read_text(encoding='utf-8')
    # Inspect the complete returned scientific table in a fresh Python process.
    probe = tmp_path/'verify-replay.py'
    probe.write_text(script+f"\nassert result[1].to_dict(orient='split') == {expected!r}\n",encoding='utf-8')
    child = subprocess.run(python_command()+[str(probe)],cwd=tmp_path,
                           capture_output=True,text=True,encoding='utf-8',timeout=40)
    assert child.returncode == 0,child.stderr
    assert response['provenance']['source'] is None
    assert response['provenance']['status'] == 'succeeded'


def test_required_dataset_plot_refuses_before_creating_an_output(tmp_path,capsys):
    output = tmp_path/'required'
    assert control.main(['run','mean_bars','--output',str(output)]) == 1
    assert '--input' in json.loads(capsys.readouterr().out)['error']
    assert not output.exists()


@pytest.mark.parametrize('action', ['power_curve', 'model_result_matrix'])
def test_source_free_export_uses_owned_output_and_replay_uses_new_output(tmp_path, capsys, monkeypatch, action):
    # Intercept the existing shared writer to test ownership without rendering
    # another scientific figure. These literal markers are not chart files.
    from PyFLASH import plotting, utils
    import pandas as pd
    recorder = '''from pathlib import Path
from PyFLASH import plotting, utils
def ownership_marker(figure, directory, name, **kwargs):
    destination = Path(directory) / (str(name) + '.export-check')
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(b'output ownership probe; not figure data')
    utils._notify_fig_saved_observers(str(destination), name, '', False)
    return str(destination)
plotting.save_fig = ownership_marker
'''
    namespace = {}
    exec(recorder.replace('plotting.save_fig = ownership_marker', ''), namespace)
    monkeypatch.setattr(plotting, 'save_fig', namespace['ownership_marker'])
    source = tmp_path/'models.csv'
    pd.DataFrame({'outcome': ['signal', 'signal'], 'predictor': ['age', 'sex'],
                  'r2': [.2, .4], 'p': [.01, .2], 'q': [.02, .3]}).to_csv(source, index=False)
    before = source.read_bytes()
    parameters = {'save': True, 'return_data': True}
    if action == 'power_curve':
        parameters.update(effect_sizes=[.2], n_range=[2, 3])
    else:
        parameters['path'] = str(source)
    output = tmp_path/'accepted'
    assert control.main(['run', action, '--params', json.dumps(parameters), '--output', str(output)]) == 0
    response = json.loads(capsys.readouterr().out.splitlines()[-1])
    receipt = response['provenance']
    markers = [row for row in receipt['outputs'] if row['path'].endswith('.export-check')]
    assert len(markers) == 1 and Path(markers[0]['path']).is_relative_to(output)
    assert receipt['parameters']['save_path'] == str(output)
    expected = response['result'][1]['data'] if action == 'power_curve' else response['result']['values']['data']
    tail = (f"\nassert result[1].to_dict(orient='split') == {expected!r}\n" if action == 'power_curve' else
            f"\nassert result['values'].to_dict(orient='split') == {expected!r}\n")
    fresh = tmp_path/'fresh'
    fresh.mkdir()
    probe = fresh/'check.py'
    probe.write_text(recorder + (output/'equivalent.py').read_text() + tail, encoding='utf-8')
    child = subprocess.run(python_command()+[str(probe)], cwd=fresh,
                           capture_output=True, text=True, encoding='utf-8', timeout=40)
    assert child.returncode == 0, child.stderr
    assert len(list((fresh/'replayed-output').glob('*.export-check'))) == 1
    assert source.read_bytes() == before
