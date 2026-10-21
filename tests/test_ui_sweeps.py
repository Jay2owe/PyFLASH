"""The browser shows the full specification curve before explicit promotion."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from streamlit.testing.v1 import AppTest
from PyFLASH.ui import jobs, workspace, sweeps, function_contracts as fc, function_workbench as fw


def make_grid(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, '_launch', lambda *args:SimpleNamespace(pid=1, poll=lambda:None))
    identity = jobs.start_sweep('PyFLASH.stats.bonferroni_correction',
        {'kwargs':{}}, {'p_value':[.01,.02], 'n_tests':[2,3]}, name='Correction choices',
        dataset_token='same', target_key='result', root=tmp_path)
    directory = tmp_path / identity
    state = jobs.run_request(directory / 'request.json')
    assert state['status'] == 'succeeded', state.get('error')
    return json.loads((directory / 'result.json').read_text()), directory


def test_native_curve_choice_matrix_and_explicit_promotion(tmp_path, monkeypatch):
    grid, directory = make_grid(tmp_path, monkeypatch)
    # AppTest's cold warning detection inspects Python stacks and Windows MIME
    # registrations. Browser render budgets are checked separately on the real app.
    app = AppTest.from_string("from PyFLASH.ui import sweeps\nimport streamlit as st\nsweeps.show_grid(st, st.session_state['grid'], namespace='test', promote=True)", default_timeout=20)
    app.session_state['grid'] = grid
    app.run()
    assert not app.exception
    charts = app.get('vega_lite_chart')
    assert len(charts) == 1
    spec = json.loads(charts[0].proto.spec)
    assert len(spec['vconcat']) == 2 and spec['resolve']['scale']['x'] == 'shared'
    assert len(app.dataframe[0].value) == 4
    receipt = json.loads((directory / 'run.json').read_text())
    assert 'promoted_cell' not in receipt
    app.selectbox(key='ui_grid_promote_test').set_value(3).run()
    app.button(key='grid_apply_test').click().run()
    assert not app.exception
    receipt = json.loads((directory / 'run.json').read_text())
    assert receipt['promoted_cell'] == grid['cells'][3]['key']
    assert receipt['promotions'][0]['parameters'] == {'n_tests':3, 'p_value':.02}
    assert receipt['request']['parameters']['choices'] == grid['choices']


def test_form_offers_choices_before_single_run_and_restores_sweep_edits(monkeypatch):
    monkeypatch.setattr(jobs, 'latest_job', lambda:None)
    calls = []
    monkeypatch.setattr(jobs, 'start_sweep', lambda *a, **k:calls.append((a,k)))
    contract = fc.find('PyFLASH.stats.bonferroni_correction')
    app = AppTest.from_string("from PyFLASH.ui import function_contracts as fc, function_workbench as fw\nfw.render(fc.find('PyFLASH.stats.bonferroni_correction'))", default_timeout=20)
    app.session_state['_ui_dataset_token'] = 'no-dataset'
    app.run()
    assert not app.exception
    app.number_input[0].set_value(.01)
    app.number_input[1].set_value(2)
    app.multiselect(key=fw._key(contract.entry, 'sweep_parameters')).set_value(['n_tests']).run()
    app.text_area(key=fw._key(contract.entry, 'sweep_values_n_tests')).set_value('2\n3').run()
    app.button(key=fw._key(contract.entry, 'sweep_run')).click().run()
    assert not app.exception and len(calls) == 1
    assert calls[0][0][2] == {'n_tests':[2,3]}
    draft = app.session_state['ui_function_drafts'][contract.entry.key]
    assert draft['sweep']['text']['n_tests'] == '2\n3'
    assert all(calls[0][1]['choice_sets']['n_tests'][name] for name in ('key','label','unit','help'))
    recovered = AppTest.from_string("from PyFLASH.ui import function_contracts as fc, function_workbench as fw\nfw.render(fc.find('PyFLASH.stats.bonferroni_correction'))", default_timeout=20)
    recovered.session_state['ui_function_drafts'] = {contract.entry.key:draft}
    recovered.session_state['_ui_dataset_token'] = 'no-dataset'
    recovered.run()
    assert not recovered.exception
    assert recovered.multiselect(key=fw._key(contract.entry, 'sweep_parameters')).value == ['n_tests']
    assert recovered.text_area(key=fw._key(contract.entry, 'sweep_values_n_tests')).value == '2\n3'
    recovered.run()
    assert recovered.session_state['ui_function_drafts'][contract.entry.key]['sweep']['text']['n_tests'] == '2\n3'


def test_promotion_refuses_changed_scientific_outputs(tmp_path, monkeypatch):
    grid, directory = make_grid(tmp_path, monkeypatch)
    cache = Path(grid['cells'][0]['receipt'])
    cell = json.loads(cache.read_text())
    (cache.parent / cell.get('root_relative', '.') / cell['result']).write_bytes(b'changed')
    with pytest.raises(ValueError, match='cannot be promoted'):
        sweeps.promote_cell(directory / 'run.json', 0)
    assert not list(directory.glob('promotion-*.json'))


def test_every_option_set_declares_stable_key_help_values_and_units():
    context = {'metrics':['Signal'], 'columns':['AnimalName','Signal'], 'markers':['DAPI']}
    for contract in fc.contracts():
        if contract.access != 'form':
            continue
        for key, entry in sweeps.option_sets(contract, context).items():
            assert key == entry['key']
            assert entry['label'] and entry['help'] and entry['unit']
            assert isinstance(entry['values'], list)
