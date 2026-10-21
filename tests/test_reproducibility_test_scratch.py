"""Pytest cleanup must preserve framework scripts created during collection."""
import json
import os
from pathlib import Path
import subprocess
from collections import namedtuple
import pytest
from reproducibility import run


def test_framework_script_survives_pytest_basetemp_cleanup(tmp_path,monkeypatch):
    import tempfile
    owner=tmp_path/'pyflash-test-job';owner.mkdir()
    monkeypatch.setattr(tempfile,'mkdtemp',lambda **_:str(owner))
    monkeypatch.setattr(tempfile,'gettempdir',lambda:str(tmp_path))
    # The subprocess produces kilobytes; the production job's separate 8 GiB
    # admission rule must not make this isolated directory test disk-dependent.
    usage=namedtuple('usage','total used free')(16*1024**3,8*1024**3,8*1024**3)
    monkeypatch.setattr(run.shutil,'disk_usage',lambda _:usage)
    environment=dict(os.environ,PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',PYTHONIOENCODING='utf-8')
    basetemp,child_env=run.full_test_environment(tmp_path,environment)
    # This is deliberately present before collection: pytest must clear it.
    assert basetemp.is_dir()
    sentinel=basetemp/'old-output';sentinel.write_text('stale')
    module=tmp_path/'test_framework_script.py'
    module.write_text('''from pathlib import Path
from streamlit.testing.v1 import AppTest
app=AppTest.from_string("import streamlit as st\\nst.text('retained framework script')")
script=Path(app._script_path)
assert script.is_file()
def test_collected_script(tmp_path):
    assert script.is_file()
    app.run(timeout=30)
    assert not app.exception
    assert app.text[0].value=='retained framework script'
''',encoding='utf-8')
    result=subprocess.run(run.python_command()+['-m','pytest',str(module),'-q',
        '--rootdir',str(tmp_path),'--confcutdir',str(tmp_path),
        '--basetemp',str(basetemp)],env=child_env,cwd=run.ROOT,
        capture_output=True,text=True,encoding='utf-8',timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    assert not sentinel.exists()
    recorded=json.loads((tmp_path/'test-scratch.json').read_text(encoding='utf-8'))
    assert Path(recorded['framework_temporary']).parent==basetemp.parent
    assert Path(recorded['framework_temporary'])!=basetemp
    assert environment.get('TMPDIR')!=child_env['TMPDIR']

def test_insufficient_full_job_space_refuses_before_test_execution(tmp_path,monkeypatch):
    import tempfile
    owner=tmp_path/'pyflash-test-job';owner.mkdir()
    monkeypatch.setattr(tempfile,'mkdtemp',lambda **_:str(owner))
    monkeypatch.setattr(tempfile,'gettempdir',lambda:str(tmp_path))
    usage=namedtuple('usage','total used free')(16*1024**3,8*1024**3+1,8*1024**3-1)
    monkeypatch.setattr(run.shutil,'disk_usage',lambda _:usage)
    with pytest.raises(RuntimeError,match='8 GB'):run.full_test_environment(tmp_path,os.environ)
    assert not owner.exists()
    recorded=json.loads((tmp_path/'test-scratch.json').read_text(encoding='utf-8'))
    assert recorded['status']=='failed-before-start'
    assert recorded['directory_absent'] is True


def test_nested_replay_process_uses_frozen_source_outside_checkout(tmp_path,monkeypatch):
    import tempfile
    source=tmp_path/'SOURCE';source.mkdir()
    editable=tmp_path/'editable';editable.mkdir()
    outside=tmp_path/'outside';outside.mkdir()
    owner=tmp_path/'pyflash-test-scratch';owner.mkdir()
    module='_pyflash_frozen_source_probe'
    (source/(module+'.py')).write_text("identity='frozen'",encoding='utf-8')
    (editable/(module+'.py')).write_text("identity='editable'",encoding='utf-8')
    monkeypatch.setattr(run,'ROOT',source)
    monkeypatch.setattr(tempfile,'mkdtemp',lambda **_:str(owner))
    monkeypatch.setattr(tempfile,'gettempdir',lambda:str(tmp_path))
    usage=namedtuple('usage','total used free')(16*1024**3,8*1024**3,8*1024**3)
    monkeypatch.setattr(run.shutil,'disk_usage',lambda _:usage)
    environment=dict(os.environ,PYTHONPATH=str(editable))
    original=dict(environment)
    _,child_env=run.full_test_environment(tmp_path,environment)
    # A replay generated in a temporary directory starts a further Python
    # process: both must resolve the frozen source before the editable install.
    child="import _pyflash_frozen_source_probe as p; print(p.identity)"
    parent=('import subprocess,sys; import _pyflash_frozen_source_probe as p; '
            'print(p.identity); '
            'r=subprocess.run([sys.executable,\"-c\",'+repr(child)+'],check=True, '
            'capture_output=True,text=True); print(r.stdout.strip())')
    result=subprocess.run([os.sys.executable,'-c',parent],env=child_env,cwd=outside,
        capture_output=True,text=True,encoding='utf-8',timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    assert result.stdout.splitlines()==['frozen','frozen']
    assert environment==original
    assert child_env['PYTHONPATH'].split(os.pathsep)==[str(source),str(editable)]
    receipt=json.loads((tmp_path/'test-scratch.json').read_text(encoding='utf-8'))
    assert receipt['source_root']==str(source)


@pytest.mark.parametrize('passed',[True,False])
def test_test_scratch_is_removed_only_after_pass(tmp_path,monkeypatch,passed):
    import tempfile
    owner=tmp_path/'pyflash-test-owned';(owner/'framework-temporary').mkdir(parents=True)
    scratch=owner/'pytest';scratch.mkdir()
    output=tmp_path/'receipt';output.mkdir()
    monkeypatch.setattr(tempfile,'gettempdir',lambda:str(tmp_path))
    run.write_json(output/'test-scratch.json',{'directory':str(owner),'status':'running'})

    record=run.finalize_full_test_scratch(output,scratch,passed)

    assert record['directory_absent'] is passed
    assert record['cleanup']==('removed-after-success' if passed else 'preserved-after-failure')
    assert owner.exists() is (not passed)


def test_test_scratch_cleanup_refuses_unowned_path(tmp_path,monkeypatch):
    import tempfile
    owner=tmp_path/'user-data';scratch=owner/'pytest';scratch.mkdir(parents=True)
    output=tmp_path/'receipt';output.mkdir()
    monkeypatch.setattr(tempfile,'gettempdir',lambda:str(tmp_path))
    run.write_json(output/'test-scratch.json',{'directory':str(owner)})

    with pytest.raises(RuntimeError,match='unowned'):
        run.finalize_full_test_scratch(output,scratch,True)
    assert owner.is_dir()


@pytest.mark.parametrize('status,removed',[('pass',True),('fail',False)])
def test_completed_stage_scratch_is_retired_only_after_pass(tmp_path,status,removed):
    output=tmp_path/'run';output.mkdir()
    scratch=output/'site';scratch.mkdir()
    (scratch/'index.html').write_text('temporary build output')
    stages=[{'name':'docs','status':status}]

    run.retire_successful_stage_output(output,'site',stages[0],stages)

    assert scratch.exists() is (not removed)
    assert (stages[0].get('scratch_cleanup') is not None) is removed


def test_stage_scratch_cleanup_refuses_path_outside_owned_run(tmp_path):
    output=tmp_path/'run';output.mkdir()
    outside=tmp_path/'user-data';outside.mkdir()
    (outside/'keep.txt').write_text('retain')

    with pytest.raises(RuntimeError,match='outside this run'):
        run.retire_successful_stage_output(output,'../user-data',{'status':'pass'},[])
    assert (outside/'keep.txt').read_text()=='retain'
