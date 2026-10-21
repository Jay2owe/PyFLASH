"""Recovery contracts use literal answers; no statistical equivalence claim."""
import csv
import hashlib
import json
from pathlib import Path
import pytest
from reproducibility import run, validation_registry as registry


def row(name, status='agree'):
    return {'contract':name, 'reference':'literal answer', 'family':'functional recovery',
            'status':status, 'pyflash_values':'[1]', 'reference_values':'[1]'}


@pytest.mark.parametrize('failed', ['first','middle','last'])
def test_failed_family_preserves_every_other_answer(tmp_path, monkeypatch, failed):
    names = ['first','middle','last']
    monkeypatch.setattr(registry,'FAMILIES',{name:'literal.'+name for name in names})
    calls=[]
    def validate(name, output):
        progress=json.loads((tmp_path/'reference-family-progress.json').read_text())
        assert progress[-1]['name']==name and progress[-1]['status']=='running'
        calls.append(name)
        if name==failed:raise RuntimeError('original failure '+name)
        return [row(name)]
    monkeypatch.setattr(registry,'validate_family',validate)
    with pytest.raises(registry.ReferenceFamilyFailure) as captured:
        registry.validate_all(tmp_path)
    assert calls==names
    assert captured.value.partial_rows==[row(name) for name in names if name!=failed]
    assert captured.value.family_failures[0]['name']==failed
    progress=json.loads((tmp_path/'reference-family-progress.json').read_text())
    for entry in progress:
        if entry['name']==failed:
            assert entry['status']=='execution-failure' and 'original failure' in entry['traceback']
        else:
            ledger=tmp_path/entry['rows_file']
            assert hashlib.sha256(ledger.read_bytes()).hexdigest()==entry['rows_sha256']
            assert json.loads(ledger.read_text())['rows']==[row(entry['name'])]


def test_empty_required_family_fails_and_later_family_runs(tmp_path,monkeypatch):
    monkeypatch.setattr(registry,'FAMILIES',{'empty':'literal.empty','later':'literal.later'})
    monkeypatch.setattr(registry,'validate_family',lambda name,output:[] if name=='empty' else [row(name)])
    with pytest.raises(registry.ReferenceFamilyFailure) as captured:registry.validate_all(tmp_path)
    assert captured.value.partial_rows==[row('later')]
    assert 'no comparisons' in str(captured.value)


def test_disagreement_is_retained_as_completed_execution(tmp_path,monkeypatch):
    monkeypatch.setattr(registry,'FAMILIES',{'wrong':'literal.wrong'})
    monkeypatch.setattr(registry,'validate_family',lambda name,output:[row(name,'disagree')])
    assert registry.validate_all(tmp_path)==[row('wrong','disagree')]
    progress=json.loads((tmp_path/'reference-family-progress.json').read_text())
    assert progress[0]['status']=='completed'
    assert json.loads((tmp_path/progress[0]['rows_file']).read_text())['rows'][0]['status']=='disagree'


def test_running_family_checkpoint_survives_interruption(tmp_path,monkeypatch):
    monkeypatch.setattr(registry,'FAMILIES',{'first':'literal.first','interrupted':'literal.interrupted'})
    def validate(name,output):
        if name=='interrupted':raise KeyboardInterrupt()
        return [row(name)]
    monkeypatch.setattr(registry,'validate_family',validate)
    with pytest.raises(KeyboardInterrupt):registry.validate_all(tmp_path)
    progress=json.loads((tmp_path/'reference-family-progress.json').read_text())
    assert [entry['status'] for entry in progress]==['completed','running']
    assert (tmp_path/progress[0]['rows_file']).is_file()


@pytest.mark.parametrize('has_initial',[False,True])
def test_numerical_failure_retains_exact_rows_and_failed_grid(tmp_path,monkeypatch,has_initial):
    initial=[row('initial')] if has_initial else []
    partial=[row('completed-family','disagree')]
    failure=registry.ReferenceFamilyFailure(partial,[{'name':'broken','module':'literal.broken','error':'original error'}])
    def execute(output,rows):
        rows.extend(initial)
        raise failure
    seen=[]
    monkeypatch.setattr(run,'_numerical_pass_impl',execute)
    monkeypatch.setattr(run,'inventory',lambda contracts:seen.extend(contracts) or [
        {'capability':'unchecked','status':'not-fully-independently-validated'}])
    with pytest.raises(registry.ReferenceFamilyFailure) as captured:run.numerical_pass(tmp_path)
    assert captured.value.partial_rows==initial+partial
    assert seen==(['initial'] if has_initial else [])
    saved=list(csv.DictReader((tmp_path/'comparisons.csv').open()))
    assert saved==initial+partial
    grid=list(csv.DictReader((tmp_path/'outcome-grid.csv').open()))
    assert any(item['status']=='execution-failure' and item['contract']=='broken' for item in grid)
    assert any(item['status']=='unexecuted-complete-contract' for item in grid)
    receipt=json.loads((tmp_path/'numerical-failure.json').read_text())
    assert not receipt['passed'] and not receipt['numerical_gate'] and not receipt['scientific_completeness_gate']


def test_family_rows_already_appended_are_not_duplicated(tmp_path,monkeypatch):
    partial=[row('family')]
    failure=registry.ReferenceFamilyFailure(partial,[{'name':'broken','module':'literal.broken','error':'failure'}])
    def execute(output,rows):rows.extend(partial);raise failure
    monkeypatch.setattr(run,'_numerical_pass_impl',execute)
    monkeypatch.setattr(run,'inventory',lambda contracts:[])
    with pytest.raises(registry.ReferenceFamilyFailure) as captured:run.numerical_pass(tmp_path)
    assert captured.value.partial_rows==partial


def test_later_failure_preserves_the_earlier_failed_family_in_the_grid(tmp_path,monkeypatch):
    earlier={'name':'original-family','module':'literal.original','status':'execution-failure','error':'first failure'}
    def execute(output,rows):
        rows.append(row('completed-family'))
        run.write_json(output/'reference-family-progress.json',[earlier])
        raise ValueError('later independent stage failed')
    monkeypatch.setattr(run,'_numerical_pass_impl',execute)
    monkeypatch.setattr(run,'inventory',lambda contracts:[])
    with pytest.raises(ValueError):run.numerical_pass(tmp_path)
    grid=list(csv.DictReader((tmp_path/'outcome-grid.csv').open()))
    assert any(item['contract']=='original-family' and item['status']=='execution-failure' for item in grid)
    receipt=json.loads((tmp_path/'numerical-failure.json').read_text())
    assert receipt['family_failures']==[earlier]
    assert receipt['comparisons_retained']==1 and 'later independent stage failed' in receipt['error']


def test_failure_before_first_comparison_still_writes_readable_artifacts(tmp_path,monkeypatch):
    def execute(output,rows):raise ValueError('input identity changed')
    monkeypatch.setattr(run,'_numerical_pass_impl',execute)
    monkeypatch.setattr(run,'inventory',lambda contracts:[])
    with pytest.raises(ValueError):run.numerical_pass(tmp_path)
    assert list(csv.DictReader((tmp_path/'comparisons.csv').open()))==[]
    assert list(csv.DictReader((tmp_path/'outcome-grid.csv').open()))[0]['status']=='execution-failure'


def test_success_returns_original_result_without_failure_artifacts(tmp_path,monkeypatch):
    expected=([row('all')],[{'status':'validated-complete-contract'}])
    monkeypatch.setattr(run,'_numerical_pass_impl',lambda output,rows:expected)
    assert run.numerical_pass(tmp_path)==expected
    assert not (tmp_path/'numerical-failure.json').exists()


def test_workflow_starts_after_failure_receipt_with_partial_rows_preserved(tmp_path,monkeypatch):
    retained=[row('initial')]
    capabilities=[{'capability':'unchecked','status':'not-fully-independently-validated'}]
    failure=RuntimeError('original reference failure')
    failure.partial_rows=retained;failure.partial_capabilities=capabilities
    def numerical(output):raise failure
    def full(output,stages,*args):
        receipt=json.loads((output/'numerical-execution-error.json').read_text())
        assert receipt['comparisons_retained']==1 and not receipt['numerical_gate']
        stages.append({'name':'independent-workflow','status':'pass'})
    monkeypatch.setattr(run,'numerical_pass',numerical)
    monkeypatch.setattr(run,'full_checks',full)
    stages=[]
    rows, actual_capabilities,error=run.execute_requested_checks(tmp_path,stages,full=True)
    assert rows==retained and actual_capabilities==capabilities
    assert 'original reference failure' in error and stages[0]['status']=='pass'


@pytest.mark.parametrize('retained_answers',[False,True])
def test_terminal_receipt_never_promotes_an_incomplete_numeric_pass(tmp_path,monkeypatch,retained_answers):
    import sys
    root=tmp_path/'source';root.mkdir()
    source=root/'fixture.txt';source.write_text('unchanged source')
    monkeypatch.setattr(run,'ROOT',root)
    monkeypatch.setattr(run,'verification_sources',lambda:[source])
    monkeypatch.setattr(run,'versions',lambda:{'scope':'literal failure ownership'})
    def checks(output,stages,**kwargs):
        run.write_json(output/'numerical-execution-error.json',{'passed':False,'error':'original failure'})
        stages.append({'name':'independent-workflow','status':'pass'})
        return [row('finished')] if retained_answers else [],[{'capability':'declared','status':'validated-complete-contract'}],'original failure'
    monkeypatch.setattr(run,'execute_requested_checks',checks)
    monkeypatch.setattr(sys,'argv',['owned-check','--full','--require-complete','--output',str(tmp_path/'receipt')])
    with pytest.raises(SystemExit) as captured:run.main()
    assert captured.value.code==1
    folder=next((tmp_path/'receipt').iterdir())
    result=json.loads((folder/'run.json').read_text())
    assert result['status']=='finished' and result['source_changes_during_run']==[]
    assert result['stages'][0]['status']=='pass'
    assert not result['passed'] and not result['numerical_gate'] and not result['scientific_completeness_gate']
