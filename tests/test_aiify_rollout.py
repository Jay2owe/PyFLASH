"""Boundary and live-backend checks for the shared assistant rollout."""
import json
from pathlib import Path
import pytest
from PyFLASH.ui.ai_assistant import RunnerSource, create_app

def test_recorded_runner_uses_real_statistical_action(tmp_path):
    source = RunnerSource(lambda: {}, tmp_path/'runs')
    result = source.run('PyFLASH.stats.bonferroni_correction', {'p_value':.03,'n_tests':2})
    assert result['ok'], result
    assert result['result'] == pytest.approx(.06)
    receipts = list((tmp_path/'runs').glob('*/run.json'))
    assert len(receipts) == 1 and json.loads(receipts[0].read_text())['ok']
    assert receipts[0].with_name('equivalent.py').is_file()

def test_current_source_is_pinned_before_a_turn(tmp_path, monkeypatch):
    monkeypatch.setenv('AIIFY_HOME',str(tmp_path/'ai'))
    app = create_app('http://127.0.0.1:9','test-token',output_root=tmp_path/'outputs')
    app.state.sessions['a'] = {'source':{'path':'original.csv','kind':'csv'},'group_col':'Group'}
    agent = app.state.agent
    agent.before_send(agent.turn('run', state={'pyflash_session':'a'}))
    app.state.sessions['a']['source']['path'] = 'later.csv'
    assert agent.current_state()['pinned_source']['source']['path'] == 'original.csv'
    assert agent.current_state()['pinned_source']['group_col'] == 'Group'
    row = agent._own_source.describe('PyFLASH.ui.services.save_pickle')
    assert agent.actions.policy.check(row['name'],row) == 'confirm'


def test_loopback_workspace_is_a_request_body_not_a_query_parameter(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from PyFLASH.ui.ai_assistant import create_app
    monkeypatch.setenv('AIIFY_HOME',str(tmp_path/'ai'))
    app=create_app('http://127.0.0.1:1','owned-test',output_root=tmp_path/'outputs')
    with TestClient(app) as client:
        response=client.post('/owned-test/workspace',json={'session':'one','source':None})
        assert response.status_code==200 and response.json()['ok']
        assert app.state.sessions['one']['source'] is None
        assert client.post('/owned-test/workspace',json={'unexpected':True}).status_code==400
