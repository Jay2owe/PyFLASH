"""A successful calculation cannot conceal a failed development-time budget."""
import json,subprocess
import pytest
from reproducibility import run

@pytest.mark.parametrize('seconds,status,passes',[
    (29.9,'pass',True),(30.,'pass',True),(30.01,'pass',False),(1.,'fail',False),
    (150.,'execution-failure',False)])
def test_development_budget_is_an_independent_workflow_gate(tmp_path,monkeypatch,seconds,status,passes):
    commands=[]
    def command(output,name,args,stages,env=None,timeout=None):
        commands.append((args,timeout))
        record={'name':name,'status':status,'elapsed_seconds':seconds,'exit_code':0 if status=='pass' else 1}
        stages.append(record)
        return record
    monkeypatch.setattr(run,'command_stage',command)
    stages=[];record=run.development_check(tmp_path,stages)
    assert record['budget_passed']==passes
    assert record['status']==('fail' if status=='pass' and not passes else status)
    assert json.loads((tmp_path/'progress.json').read_text())==stages
    assert commands[0][1]==150
    assert ['--disable-plugin-autoload','-m','not slow'] in [commands[0][0][i:i+3] for i in range(len(commands[0][0])-2)]

def test_command_deadline_preserves_partial_log_and_failure_receipt(tmp_path,monkeypatch):
    def interrupted(args,*,stdout,timeout,**kwargs):
        stdout.write('completed first calculation\n');stdout.flush()
        raise subprocess.TimeoutExpired(args,timeout)
    monkeypatch.setattr(run.subprocess,'run',interrupted)
    stages=[];record=run.command_stage(tmp_path,'interrupted',['owned-check'],stages,timeout=1)
    assert record['status']=='execution-failure'
    assert 'timed out' in record['error']
    assert (tmp_path/'interrupted.log').read_text()=='completed first calculation\n'
    assert json.loads((tmp_path/'progress.json').read_text())==stages
