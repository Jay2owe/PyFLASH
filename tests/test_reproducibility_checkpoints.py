"""An interrupted calculation retains identities without becoming a pass."""
import hashlib,json,subprocess,sys,time
from contextvars import ContextVar
from pathlib import Path
from types import ModuleType
import pytest
import psutil
from reproducibility import run


@pytest.fixture(autouse=True)
def private_source_evidence_store(tmp_path,monkeypatch):
    from reproducibility import compact_evidence
    monkeypatch.setattr(run,'SOURCE_EVIDENCE_STORE',tmp_path/'source-evidence')
    monkeypatch.setattr(compact_evidence,'available_ram',lambda:8*1024**3)


def test_terminated_calculation_keeps_starting_receipt(tmp_path):
    root=tmp_path/'owned-root';root.mkdir();source=root/'fixture.txt';source.write_text('original source')
    output=tmp_path/'checks'
    program=f'''
from pathlib import Path
import os,json,sys,time
from reproducibility import run
run.ROOT=Path({str(root)!r})
run.verification_sources=lambda: [run.ROOT/'fixture.txt']
run.versions=lambda: {{'test_scope':'receipt ownership only'}}
def waiting(output,stages,**kwargs):
    (output/'ready').write_text(json.dumps({{'pid':os.getpid()}}),encoding='utf-8')
    while True:time.sleep(.05)
run.execute_requested_checks=waiting
sys.argv=['owned-check','--output',{str(output)!r},'--require-complete']
run.main()
'''
    child=subprocess.Popen(run.python_command(native_metadata=True)+['-c',program],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    owned = None
    try:
        deadline=time.monotonic()+20;ready=[]
        while time.monotonic()<deadline and child.poll() is None:
            ready=list(output.glob('*/ready'))
            if ready:break
            time.sleep(.05)
        assert ready,'Owned calculation did not reach its checkpoint.'
        folder=ready[0].parent
        started=json.loads((folder/'run-started.json').read_text(encoding='utf-8'))
        pending=json.loads((folder/'run.json').read_text(encoding='utf-8'))
        actual_pid = json.loads(ready[0].read_text(encoding='utf-8'))['pid']
        parent = psutil.Process(child.pid)
        owned = next((process for process in [parent, *parent.children(recursive=True)]
                      if process.pid == actual_pid), None)
        assert owned is not None, 'The receipt writer must belong to the launched process tree.'
        assert pending==started and started['owner_pid']==actual_pid
        assert started['status']=='running' and started['passed'] is False
        assert started['numerical_gate'] is False and started['scientific_completeness_gate'] is False
        assert started['parameters']['require_complete'] is True
        assert started['sources']==[{'path':'fixture.txt','sha256':hashlib.sha256(source.read_bytes()).hexdigest()}]
        owned.terminate();owned.wait(timeout=10);child.wait(timeout=10)
        assert json.loads((folder/'run-started.json').read_text(encoding='utf-8'))==started
        assert json.loads((folder/'run.json').read_text(encoding='utf-8'))['passed'] is False
    finally:
        if owned is not None and owned.is_running():
            owned.kill();owned.wait(timeout=10)
        if child.poll() is None:child.kill()
        child.communicate(timeout=10)


@pytest.mark.parametrize('change_source',(False,True))
def test_terminal_receipt_authenticates_outputs_and_refuses_source_changes(tmp_path,monkeypatch,change_source):
    root=tmp_path/'owned-root';root.mkdir();source=root/'fixture.txt';source.write_text('original source')
    monkeypatch.setattr(run,'ROOT',root)
    monkeypatch.setattr(run,'verification_sources',lambda:[source])
    monkeypatch.setattr(run,'versions',lambda:{'test_scope':'receipt ownership only'})
    def checks(output,stages,**kwargs):
        if change_source:source.write_text('changed source')
        return [{'status':'agree'}],[{'status':'validated-complete-contract'}],None
    monkeypatch.setattr(run,'execute_requested_checks',checks)
    monkeypatch.setattr(sys,'argv',['owned-check','--output',str(tmp_path/'checks'),'--require-complete'])
    if change_source:
        with pytest.raises(SystemExit) as error:run.main()
        assert error.value.code==1
    else:run.main()
    folder=next((tmp_path/'checks').iterdir())
    started=json.loads((folder/'run-started.json').read_text(encoding='utf-8'))
    finished=json.loads((folder/'run.json').read_text(encoding='utf-8'))
    assert started['passed'] is False and started['status']=='running'
    assert 'working_tree_status' not in started
    assert len(started['working_tree_status_sha256'])==64
    assert started['snapshot_sources_expected_count']==1
    assert len(started['snapshot_sources_expected_sha256'])==64
    assert finished['status']=='finished' and finished['passed'] is (not change_source)
    assert finished['source_changes_during_run']==(['fixture.txt'] if change_source else [])
    assert finished['numerical_gate'] is True
    assert finished['scientific_completeness_gate'] is (not change_source)
    assert 'run.json' not in {row['path'] for row in finished['outputs']}
    assert finished['source_snapshot_cleanup']['status']==(
        'preserved-after-source-change' if change_source else 'removed-after-verified-recovery-packet')
    assert (folder/'sources').exists() is change_source
    assert not (folder/'snapshot-progress.json').exists() if not change_source else True
    if not change_source:
        from reproducibility import compact_evidence
        restored=tmp_path/'restored-producing-code'
        compact_evidence.restore(folder/'source-packet/version.jsonl.gz',run.SOURCE_EVIDENCE_STORE,restored)
        source.write_text('a later implementation changed the working tree')
        assert (restored/'fixture.txt').read_text()=='original source'
    for row in finished['outputs']:
        assert hashlib.sha256((folder/row['path']).read_bytes()).hexdigest()==row['sha256']


def test_unreadable_output_finishes_failed_receipt_and_retains_other_hashes(tmp_path, monkeypatch):
    root = tmp_path / 'owned-root'
    root.mkdir()
    source = root / 'fixture.txt'
    source.write_text('original source')
    monkeypatch.setattr(run, 'ROOT', root)
    monkeypatch.setattr(run, 'verification_sources', lambda: [source])
    monkeypatch.setattr(run, 'versions', lambda: {'test_scope': 'receipt ownership only'})
    def checks(output, stages, **kwargs):
        (output / 'locked-temporary').write_text('retained failed consumer scratch')
        (output / 'accepted.json').write_text('{"independent":"original"}')
        return [{'status': 'agree'}], [{'status': 'validated-complete-contract'}], None
    monkeypatch.setattr(run, 'execute_requested_checks', checks)
    original_digest = run.sha256
    def inaccessible(path):
        if Path(path).name == 'locked-temporary':
            raise PermissionError('Owned failed process still holds its temporary file.')
        return original_digest(path)
    monkeypatch.setattr(run, 'sha256', inaccessible)
    monkeypatch.setattr(sys, 'argv', ['owned-check', '--output', str(tmp_path / 'checks'), '--require-complete'])
    with pytest.raises(SystemExit) as failure:
        run.main()
    assert failure.value.code == 1
    folder = next((tmp_path / 'checks').iterdir())
    finished = json.loads((folder / 'run.json').read_text(encoding='utf-8'))
    assert finished['status'] == 'finished' and not finished['passed']
    assert not finished['scientific_completeness_gate']
    assert finished['output_authentication_errors'][0]['path'] == 'locked-temporary'
    assert 'Output authentication failed' in finished['error']
    assert 'locked-temporary' in (folder / 'DIFFERENCES.md').read_text(encoding='utf-8')
    assert (folder / 'locked-temporary').read_text() == 'retained failed consumer scratch'
    for row in finished['outputs']:
        assert original_digest(folder / row['path']) == row['sha256']
    assert 'accepted.json' in {row['path'] for row in finished['outputs']}


def test_workflow_configuration_failure_gets_terminal_receipt(tmp_path, monkeypatch):
    root=tmp_path/'owned-root';root.mkdir();source=root/'fixture.txt';source.write_text('source')
    monkeypatch.setattr(run,'ROOT',root)
    monkeypatch.setattr(run,'verification_sources',lambda:[source])
    monkeypatch.setattr(run,'versions',lambda:{'test_scope':'configuration failure'})
    workflow=ModuleType('reproducibility.workflow')
    def configure(*args,**kwargs):
        raise RuntimeError('reference setup failed')
    workflow.configure=configure
    workflow._REQUEST=ContextVar('test_request')
    monkeypatch.setitem(sys.modules,'reproducibility.workflow',workflow)
    monkeypatch.setattr(sys,'argv',['owned-check','--output',str(tmp_path/'checks'),'--require-complete'])

    with pytest.raises(SystemExit) as failure:
        run.main()

    assert failure.value.code==1
    folder=next((tmp_path/'checks').iterdir())
    receipt=json.loads((folder/'run.json').read_text(encoding='utf-8'))
    assert receipt['status']=='finished' and not receipt['passed']
    assert 'reference setup failed' in receipt['error']
    assert not receipt['scientific_completeness_gate']
    assert receipt['finalization_report_failed'] is False
    assert 'run is incomplete' not in (folder/'DIFFERENCES.md').read_text(encoding='utf-8')


def test_successful_stage_log_is_compacted_but_failure_log_is_retained(tmp_path):
    output=tmp_path/'stages';output.mkdir()
    passed=run._command_stage(output,'passing',[sys.executable,'-c',"print('compact success proof')"],[])
    assert passed['status']=='pass' and passed['log_retained'] is False
    assert passed['log'] is None and passed['log_sha256']
    assert passed['log_excerpt'].strip()=='compact success proof'
    assert not (output/'passing.log').exists()

    failed=run._command_stage(output,'failing',
        [sys.executable,'-c',"print('diagnose this failure'); raise SystemExit(7)"],[])
    assert failed['status']=='fail' and failed['log_retained'] is True
    assert (output/failed['log']).read_text(encoding='utf-8').strip()=='diagnose this failure'
