"""A failed built consumer cannot hide the other required artifact checks."""
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import zipfile
import pytest
from scripts import check_distribution_consumers as M


@pytest.mark.parametrize('failure', ['test-failure', 'required-skip', 'missing-report', 'timeout'])
def test_finished_failure_retains_log_and_never_counts_as_pass(tmp_path, failure):
    report=tmp_path/'owned-tests.xml'
    flags={'test-failure': 'failures="1"', 'required-skip': 'skipped="1"'}
    text='<testsuites><testsuite tests="1" '+flags.get(failure,'')+'/></testsuites>'
    script="import pathlib,time; print('original consumer output',flush=True); "
    if failure not in {'timeout','missing-report'}:
        script+=f'pathlib.Path({str(report)!r}).write_text({text!r}); '
    if failure=='timeout':script+='time.sleep(20)'
    actual=Path(sys.prefix)/'python.exe'
    command=[str(actual) if os.name=='nt' and actual.is_file() else sys.executable,'-c',script]
    result=M.execute_check(command,directory=tmp_path,environment=os.environ.copy(),
        owner=tmp_path,identity='owned',required=1,timeout=3 if failure=='timeout' else 15)
    assert result['status']=='finished' and not result['passed']
    assert 'original consumer output' in (tmp_path/'owned.log').read_text()
    assert json.loads((tmp_path/'owned-stage.json').read_text())==result
    if failure=='timeout':assert result['error'].startswith('TimeoutExpired:')


def test_all_declared_source_and_wheel_checks_run_after_first_failure(tmp_path, monkeypatch):
    # This synthetic archive has only four tiny files. Exercise orchestration
    # independently of current free space; the separate admission test below
    # retains the real package's full five-GiB refusal boundary.
    from types import SimpleNamespace
    monkeypatch.setattr(M.shutil, 'disk_usage', lambda path: SimpleNamespace(free=8*1024**3))
    dist=tmp_path/'dist';dist.mkdir()
    check=dict(kind='pytest',argv=['{python}','-m','pytest','tests/original.py','-q'],
               min_passed=1,timeout_seconds=15)
    files={'architecture.yaml':json.dumps({'checks':[dict(check,id=name) for name in M.CHECK_IDS]}).encode(),
           'tests/original.py':b'original test', 'PyFLASH/__init__.py':b'original source',
           'reproducibility/fixtures/ordinal_constant_reference.json':b'{"rows":["original fixture"]}'}
    with tarfile.open(dist/'original.tar.gz','w:gz') as archive:
        for name,data in files.items():
            member=tarfile.TarInfo('original/'+name);member.size=len(data)
            archive.addfile(member,io.BytesIO(data))
    with zipfile.ZipFile(dist/'original.whl','w') as wheel:
        wheel.writestr('PyFLASH/__init__.py',b'original wheel')
    calls=[]
    def execute(command, **kwargs):
        required=kwargs['directory']/'reproducibility/fixtures/ordinal_constant_reference.json'
        assert required.read_bytes()==files['reproducibility/fixtures/ordinal_constant_reference.json']
        assert kwargs['directory'].parent == kwargs['owner']
        assert kwargs['owner'] != tmp_path/'consumer'
        assert '--basetemp='+str(kwargs['owner']/(kwargs['identity']+'-pytest-data')) in command
        assert '--junitxml='+str(kwargs['owner']/(kwargs['identity']+'-tests.xml')) in command
        assert kwargs['environment']['TEMP']==str(kwargs['owner']/(kwargs['identity']+'-framework-temporary'))
        assert kwargs['environment']['PYTEST_DISABLE_PLUGIN_AUTOLOAD']=='1'
        assert kwargs['environment']['PYTHONDONTWRITEBYTECODE']=='1'
        assert '-o' in command
        assert 'cache_dir='+str(kwargs['owner']/(kwargs['identity']+'-cache')) in command
        calls.append(kwargs['identity'])
        return dict(name=kwargs['identity'],status='finished',passed=len(calls)>1,
                    error='retained original failure' if len(calls)==1 else None)
    monkeypatch.setattr(M,'execute_check',execute)
    owner=tmp_path/'consumer'
    monkeypatch.setattr(sys,'argv',['consumers','--dist-dir',str(dist),'--output',str(owner)])
    with pytest.raises(SystemExit) as result:M.main()
    assert result.value.code==1
    assert calls==[mode+'-'+name for mode in ('source','wheel') for name in M.CHECK_IDS]
    record=json.loads((owner/'run.json').read_text())
    assert record['status']=='finished' and not record['passed']
    assert record['failed_stages']==[calls[0]]
    assert len(record['stages'])==4
    assert record['source_changes']==record['wheel_changes']==[]
    work=Path(record['work_directory'])
    assert work.is_dir() and (work/'source-download/tests/original.py').read_bytes()==b'original test'


def test_real_consumer_admission_refuses_before_creating_output(tmp_path, monkeypatch):
    from types import SimpleNamespace
    dist = tmp_path / 'dist'
    dist.mkdir()
    (dist / 'original.tar.gz').write_bytes(b'not expanded before admission')
    (dist / 'original.whl').write_bytes(b'not expanded before admission')
    owner = tmp_path / 'consumer'
    monkeypatch.setattr(M.shutil, 'disk_usage', lambda path: SimpleNamespace(free=5*1024**3-1))
    monkeypatch.setattr(sys, 'argv', ['consumers', '--dist-dir', str(dist), '--output', str(owner)])
    with pytest.raises(RuntimeError, match='5 GiB'):
        M.main()
    assert not owner.exists()
