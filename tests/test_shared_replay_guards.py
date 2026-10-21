"""All exported scripts refuse changed identities before producing a result."""
import hashlib
import importlib.metadata as metadata
from pathlib import Path
import pytest
from PyFLASH import _replay, _persistence, dependencies
from PyFLASH.ui import workspace


@pytest.fixture
def guard_state(tmp_path, monkeypatch):
    source=tmp_path/'source.csv';source.write_bytes(b'original input')
    extra=tmp_path/'extra.csv';extra.write_bytes(b'extra original')
    state={'code':{'engine.py':'original'},'dependency':'1.0'}
    monkeypatch.setattr(_replay,'code_identity',lambda:dict(state['code']))
    monkeypatch.setattr(_persistence,'code_identity',lambda:dict(state['code']))
    monkeypatch.setattr(dependencies,'check',lambda:[{'package':'owned-replay-dependency','version':'1.0'}])
    original=metadata.version
    monkeypatch.setattr(metadata,'version',lambda name:state['dependency'] if name=='owned-replay-dependency' else original(name))
    return source,extra,state


def script(source,extra):
    records=[{'path':str(extra),'sha256':hashlib.sha256(extra.read_bytes()).hexdigest()}]
    return '\n'.join(_replay.guard_lines(source=str(source),input_records=records)+['result_produced = True'])


def test_unchanged_input_code_and_dependencies_reach_the_result(guard_state):
    source,extra,_=guard_state;namespace={}
    exec(script(source,extra),namespace)
    assert namespace['result_produced'] is True


@pytest.mark.parametrize('change',('source','extra','code-change','code-add','code-delete','dependency','package'))
def test_changed_identity_refuses_before_any_result(guard_state,change,monkeypatch):
    source,extra,state=guard_state;captured=script(source,extra);namespace={}
    if change=='source':source.write_bytes(b'changed input!')
    elif change=='extra':extra.write_bytes(b'changed extra!')
    elif change=='code-change':state['code']['engine.py']='changed'
    elif change=='code-add':state['code']['new.py']='added'
    elif change=='code-delete':state['code'].clear()
    elif change=='dependency':state['dependency']='2.0'
    else:
        original=metadata.version
        monkeypatch.setattr(metadata,'version',lambda name:'changed' if name=='PyFLASH-analysis' else original(name))
    with pytest.raises(AssertionError,match='changed'):exec(captured,namespace)
    assert 'result_produced' not in namespace


def test_captured_consumed_hash_is_used_instead_of_rehashing_new_bytes(guard_state):
    source,_,_=guard_state
    consumed=hashlib.sha256(source.read_bytes()).hexdigest()
    source.write_bytes(b'replaced after load')
    captured='\n'.join(_replay.guard_lines(source=str(source),source_sha256=consumed)+['result_produced = True'])
    namespace={}
    with pytest.raises(AssertionError,match='Input content changed'):exec(captured,namespace)
    assert 'result_produced' not in namespace


@pytest.mark.parametrize('kind',('plot','action'))
def test_ui_builders_call_the_same_header_owner(tmp_path,monkeypatch,kind):
    source=tmp_path/'summary.csv';source.write_text('AnimalName,Condition,Signal\na,A,1\n',encoding='utf-8')
    called=[];original=_replay.guard_lines
    def observe(**kwargs):called.append(kwargs);return original(**kwargs)
    monkeypatch.setattr(_replay,'guard_lines',observe)
    if kind=='plot':
        result=workspace.equivalent_script(source,'mean_bars',{'data_cols':['Signal']},source_kind='csv')
    else:
        result=workspace.equivalent_action_script('PyFLASH.stats.bonferroni_correction',{'p_value':.01,'n_tests':3})
    assert len(called)==1
    assert result.count('CODE_IDENTITY =')==1 and result.count('DEPENDENCIES =')==1
