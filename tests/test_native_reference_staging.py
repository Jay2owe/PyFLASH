"""Synced outputs retain complete native evidence without active checkpoint churn."""
import json
from pathlib import Path
import subprocess
import pytest
from reproducibility import reference_runtime

def configure(tmp_path,monkeypatch):
    monkeypatch.setattr(reference_runtime,'ensure',lambda:tmp_path/'runtime')
    monkeypatch.setattr(reference_runtime,'_needs_local_staging',lambda output: True)
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'local'))

def test_synced_native_reference_stages_progress_then_retains_results(tmp_path,monkeypatch):
    configure(tmp_path,monkeypatch)
    output=tmp_path/'Dropbox'/'proof'
    def completed(command,**options):
        source,answer=Path(command[-3]),Path(command[-2])
        assert source.parent!=output and 'reference-jobs' in source.parts
        assert json.loads(source.read_text())==[{'key':'ordinary','code':'1+1'}]
        answer.write_text(json.dumps({'rows':[{'key':'ordinary','status':'executed','values':[2]}]}))
        answer.with_suffix('.progress.jsonl').write_text('retained row\n')
        return subprocess.CompletedProcess(command,0,'finished','')
    monkeypatch.setattr(subprocess,'run',completed)
    result=reference_runtime.execute_queries([{'key':'ordinary','code':'1+1'}],output,name='staged')
    assert result['rows'][0]['values']==[2]
    assert (output/'staged-results.progress.jsonl').read_text()=='retained row\n'
    staging=json.loads((output/'staged-staging.json').read_text())
    assert Path(staging['directory']).is_dir()
    assert (output/'staged-results.json').is_file()
    execution=json.loads((output/'staged-execution.json').read_text())
    assert execution['status']=='completed' and execution['returncode']==0
    assert execution['timeout_seconds']==180 and execution['requested_queries']==1

def test_synced_native_reference_timeout_retains_partial_staged_evidence(tmp_path,monkeypatch):
    configure(tmp_path,monkeypatch)
    output=tmp_path/'Dropbox'/'proof'
    def stopped(command,**options):
        answer=Path(command[-2])
        answer.with_suffix('.partial.json').write_text('{"complete":false}')
        answer.with_suffix('.progress.jsonl').write_text('retained completed query\n')
        raise subprocess.TimeoutExpired(command,180,output=b'checkpoint retained\n')
    monkeypatch.setattr(subprocess,'run',stopped)
    with pytest.raises(subprocess.TimeoutExpired):
        reference_runtime.execute_queries([{'key':'ordinary','code':'1+1'}],output,name='staged')
    assert (output/'staged-results.partial.json').read_text()=='{"complete":false}'
    assert (output/'staged-results.progress.jsonl').read_text()=='retained completed query\n'
    assert (output/'staged-timeout.json').is_file()
