"""Long reference work keeps logs and completed queries when its deadline expires."""
import json
import subprocess
import pytest
from reproducibility import reference_runtime

def test_native_reference_timeout_retains_identity_and_partial_output(tmp_path, monkeypatch):
    monkeypatch.setattr(reference_runtime, 'ensure', lambda: tmp_path/'runtime')
    def stopped(command, **options):
        assert options['timeout'] == 600
        raise subprocess.TimeoutExpired(command, 600, output=b'completed query 1\n', stderr=b'waiting\n')
    monkeypatch.setattr(subprocess, 'run', stopped)
    queries = [{'key':'first', 'code':'1+1'}]
    output = tmp_path/'proof'
    with pytest.raises(subprocess.TimeoutExpired):
        reference_runtime.execute_queries(queries, output, name='deadline', timeout=600)
    assert json.loads((output/'deadline-queries.json').read_text()) == queries
    assert (output/'deadline.log').read_text() == 'completed query 1\nwaiting\n'
    receipt=json.loads((output/'deadline-timeout.json').read_text())
    assert receipt['status']=='timed-out' and receipt['timeout_seconds']==600
    assert receipt['partial_results_file'].endswith('deadline-results.partial.json')
    execution=json.loads((output/'deadline-execution.json').read_text())
    assert execution['status']=='timed-out' and execution['timeout_seconds']==600
    assert execution['requested_queries']==1 and execution['elapsed_seconds']>=0
