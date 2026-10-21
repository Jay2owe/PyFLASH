import json
import pytest
from reproducibility import experiment_path_contract as contract

def test_all_original_lookup_inputs_and_answers_remain_frozen():
    contract.check_identity()
    assert len(contract.cases())==38
    for api in contract.APIS:assert len(contract.required_keys(api))==38

def test_relative_output_paths_preserve_all_lookup_envelopes(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    for index,case in enumerate(contract.cases()):
        assert contract.production(case,'relative-output/'+str(index))==contract.answer(case)

@pytest.mark.parametrize('alteration',['input','answer','before-hash'])
def test_changed_evidence_is_refused_before_folder_lookup(tmp_path,monkeypatch,alteration):
    fixture=json.loads(contract.FIXTURE.read_text(encoding='utf-8'))
    if alteration=='input':fixture['rows'][0]['query']='unreviewed-folder'
    elif alteration=='answer':fixture['rows'][0]['expected']['layout']='unreviewed-layout'
    else:fixture['before_sha256']='0'*64
    target=tmp_path/'changed.json';target.write_text(json.dumps(fixture),encoding='utf-8')
    monkeypatch.setattr(contract,'FIXTURE',target)
    monkeypatch.setattr(contract,'production',lambda *args:pytest.fail('Altered evidence reached a production call.'))
    with pytest.raises(ValueError):contract.validate(tmp_path/'run')

def test_one_failure_retains_completed_envelopes_and_attempts_later_inputs(tmp_path,monkeypatch):
    cases=contract.cases()[:3];calls=[]
    monkeypatch.setattr(contract,'check_identity',lambda:None)
    monkeypatch.setattr(contract,'cases',lambda:cases)
    def produce(case,output):
        calls.append(case['key'])
        if len(calls)==2:raise RuntimeError('retained folder failure')
        if len(calls)==3:
            prior=json.loads((tmp_path/'experiment-path-paired.json').read_text())
            assert len(prior['rows'])==6 and prior['rows'][3]['error']=='RuntimeError: retained folder failure'
        return contract.answer(case)
    monkeypatch.setattr(contract,'production',produce)
    rows=contract.validate(tmp_path)
    assert calls==[case['key'] for case in cases]
    assert [row['status'] for row in rows]==['agree']*3+['disagree']*3+['agree']*3

def test_failure_on_an_unsupported_input_is_not_counted_as_agreement(tmp_path,monkeypatch):
    case=next(case for case in contract.cases() if case['expected'] is None)
    monkeypatch.setattr(contract,'check_identity',lambda:None)
    monkeypatch.setattr(contract,'cases',lambda:[case])
    def failure(*args):raise RuntimeError('lookup did not execute')
    monkeypatch.setattr(contract,'production',failure)
    assert all(row['status']=='disagree' for row in contract.validate(tmp_path))
