"""A failed reference must not suppress independent executable workflow gates."""
import pytest
from reproducibility import run

@pytest.mark.parametrize('mode',['full','browser','numerical-only'])
def test_reference_failure_is_retained_while_requested_checks_finish(tmp_path,monkeypatch,mode):
    calls=[]
    def numerical(output):raise RuntimeError('retained native timeout')
    monkeypatch.setattr(run,'numerical_pass',numerical)
    monkeypatch.setattr(run,'inventory',lambda:[{'capability':'unexecuted','status':'not-fully-independently-validated'}])
    def workflow(output,stages,port,*args):
        calls.append((output,port,args));stages.append({'status':'pass','name':'independent-workflow'})
    monkeypatch.setattr(run,'full_checks',workflow)
    monkeypatch.setattr(run,'browser_checks',workflow)
    stages=[]
    rows,capabilities,error=run.execute_requested_checks(tmp_path,stages,full=mode=='full',browser_only=mode=='browser',port=8589,real_data='trusted')
    assert rows==[] and capabilities[0]['status']=='not-fully-independently-validated'
    assert 'retained native timeout' in error
    assert bool(calls)==(mode!='numerical-only')
    if mode=='full':assert calls==[(tmp_path,8589,('trusted',))]

def test_both_stage_errors_are_preserved_without_certifying_partial_answers(tmp_path,monkeypatch):
    def numerical(output):raise ValueError('native failure')
    def full(*args):raise ValueError('workflow failure')
    monkeypatch.setattr(run,'numerical_pass',numerical)
    monkeypatch.setattr(run,'full_checks',full)
    monkeypatch.setattr(run,'inventory',lambda:[])
    rows,capabilities,error=run.execute_requested_checks(tmp_path,[],full=True)
    assert not rows and not capabilities
    assert 'native failure' in error and 'workflow failure' in error

def test_successful_reference_and_workflow_answers_are_retained(tmp_path,monkeypatch):
    monkeypatch.setattr(run,'numerical_pass',lambda output:([{'status':'agree'}],[{'status':'validated-complete-contract'}]))
    monkeypatch.setattr(run,'full_checks',lambda output,stages,*args:stages.append({'status':'pass'}))
    stages=[]
    rows,capabilities,error=run.execute_requested_checks(tmp_path,stages,full=True)
    assert rows==[{'status':'agree'}] and capabilities==[{'status':'validated-complete-contract'}]
    assert error is None and stages==[{'status':'pass'}]
