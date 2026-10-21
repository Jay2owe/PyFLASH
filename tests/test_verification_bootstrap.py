"""Owned check launchers preserve arguments, interpreter and genuine exit codes."""
from pathlib import Path
import json
import subprocess
import sys
import pytest
from reproducibility import check_bootstrap

BOOTSTRAP=Path(check_bootstrap.__file__)

def interpreter():
    actual=Path(sys.prefix)/'python.exe'
    return str(actual) if actual.is_file() else sys.executable

def test_verification_expression_preserves_arguments_and_interpreter():
    result=subprocess.run([interpreter(),str(BOOTSTRAP),'-c',
        'import json,sys;print(json.dumps([sys.argv,sys.prefix]))','literal $(text)','two words'],
        capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    argv,prefix=json.loads(result.stdout)
    assert argv==['-c','literal $(text)','two words']
    assert Path(prefix)==Path(sys.prefix)


def test_verification_disables_cache_writes_in_its_owned_interpreter():
    result=subprocess.run([interpreter(),'-I',str(BOOTSTRAP),'-c',
        'import json,sys;print(json.dumps(sys.dont_write_bytecode))'],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout) is True

def test_verification_script_preserves_a_nonzero_exit_and_stderr(tmp_path):
    source=tmp_path/'failure.py'
    source.write_text('import sys\nprint("retained diagnostic",file=sys.stderr)\nraise SystemExit(7)\n',encoding='utf-8')
    result=subprocess.run([interpreter(),str(BOOTSTRAP),str(source)],capture_output=True,text=True,timeout=30)
    assert result.returncode==7 and result.stderr.strip()=='retained diagnostic'

def test_verification_module_preserves_module_execution(tmp_path):
    result=subprocess.run([interpreter(),str(BOOTSTRAP),'-m','json.tool','--compact'],
        input='{ "value": 3 }',capture_output=True,text=True,timeout=30)
    assert result.returncode==0 and result.stdout.strip()=='{"value":3}'

def test_native_windows_probe_uses_the_existing_fallback(monkeypatch):
    monkeypatch.setattr(check_bootstrap.sys,'platform','win32')
    monkeypatch.setattr(check_bootstrap.platform,'_wmi_query',lambda *args: ('unexpected',),raising=False)
    monkeypatch.setattr(check_bootstrap.platform,'_syscmd_ver',lambda *args: ('unexpected',),raising=False)
    check_bootstrap.native_windows_information()
    with pytest.raises(OSError):check_bootstrap.platform._wmi_query('OS','Version')
    assert check_bootstrap.platform._syscmd_ver()==('','','')
    assert check_bootstrap.platform._syscmd_ver('Windows','11','10.0')==('Windows','11','10.0')

def test_non_windows_verification_leaves_platform_queries_unchanged(monkeypatch):
    monkeypatch.setattr(check_bootstrap.sys,'platform','linux')
    original=lambda *args: ('unchanged',)
    monkeypatch.setattr(check_bootstrap.platform,'_wmi_query',original,raising=False)
    check_bootstrap.native_windows_information()
    assert check_bootstrap.platform._wmi_query is original

def test_metadata_fallback_is_opt_in_and_preserves_product_launch_command():
    from reproducibility.run import python_command
    import os
    regular=python_command()
    checks=python_command(native_metadata=True)
    assert len(regular)==1
    assert checks[0]==regular[0]
    if os.name=='nt':assert checks[1:]==[str(BOOTSTRAP)]
    else:assert checks==regular


def test_plain_pytest_child_uses_owned_metadata_fallback_and_writes_complete_junit(tmp_path):
    """The declared verifier starts plain pytest, so its child needs the fallback."""
    import os
    import xml.etree.ElementTree as ET
    root=Path(__file__).resolve().parents[1]
    (tmp_path/'conftest.py').write_bytes((root/'tests/conftest.py').read_bytes())
    source=tmp_path/'test_child_metadata.py'
    source.write_text('import platform,sys\n'
        'def test_owned_metadata():\n'
        '    if sys.platform == "win32":\n'
        '        assert platform._wmi_query.__module__ == "reproducibility.check_bootstrap"\n'
        '    assert isinstance(platform.node(),str)\n',encoding='utf-8')
    environment=dict(os.environ)
    environment.pop('PYTEST_DISABLE_PLUGIN_AUTOLOAD',None)
    environment.pop('PYTEST_ADDOPTS',None)
    environment['PYTHONPATH']=str(root)
    report=tmp_path/'child.xml'
    result=subprocess.run([interpreter(),'-m','pytest','-c',str(root/'pyproject.toml'),
        str(source),'-q','--rootdir',str(tmp_path),'--confcutdir',str(tmp_path),
        '--junitxml='+str(report)],cwd=tmp_path,env=environment,
        capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    suites=ET.parse(report).getroot().findall('testsuite')
    assert sum(int(s.get('tests',0)) for s in suites)==1
    assert not sum(int(s.get(k,0)) for s in suites for k in ('failures','errors','skipped'))
