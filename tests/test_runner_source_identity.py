"""Source/dependency identity and stale resident request refusal."""
import hashlib
from types import SimpleNamespace
import pytest
import PyFLASH
from PyFLASH import _persistence,dependencies
from PyFLASH import _runner_identity as identity

@pytest.fixture
def source_identity(tmp_path,monkeypatch):
    package=tmp_path/'package';package.mkdir();(package/'engine.py').write_text('original',encoding='utf-8')
    kit=tmp_path/'kit';kit.mkdir();(kit/'__init__.py').write_text('kit',encoding='utf-8');(kit/'worker.py').write_text('worker',encoding='utf-8')
    runner=tmp_path/'runner.py';runner.write_text('runner',encoding='utf-8');installed={'version':'1.0'}
    def inventory():return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in package.glob('*.py')}
    monkeypatch.setattr(_persistence,'code_identity',inventory)
    monkeypatch.setattr(PyFLASH,'_LOADED_SOURCE_IDENTITY',inventory())
    monkeypatch.setattr(identity,'find_spec',lambda name:SimpleNamespace(origin=str(kit/'__init__.py')))
    monkeypatch.setattr(identity,'version',lambda name:'1.0')
    monkeypatch.setattr(dependencies,'check',lambda:[{'package':'owned-dependency','version':installed['version']}])
    return package,kit,runner,installed

def test_unchanged_sources_reuse_identity(source_identity):
    _,_,runner,_=source_identity
    assert identity.runner_identity(runner)==identity.runner_identity(runner)

@pytest.mark.parametrize('change',('runner','kit-change','kit-add','kit-delete','dependency'))
def test_every_runner_worker_dependency_change_selects_new_identity(source_identity,change):
    _,kit,runner,installed=source_identity;before=identity.runner_identity(runner)
    if change=='runner':runner.write_text('changed',encoding='utf-8')
    elif change=='kit-change':(kit/'worker.py').write_text('changed',encoding='utf-8')
    elif change=='kit-add':(kit/'new.py').write_text('added',encoding='utf-8')
    elif change=='kit-delete':(kit/'worker.py').unlink()
    else:installed['version']='2.0'
    assert identity.runner_identity(runner)!=before

@pytest.mark.parametrize('change',('change','add','delete'))
def test_loaded_package_change_refuses_until_fresh_import(source_identity,change):
    package,_,runner,_=source_identity
    if change=='change':(package/'engine.py').write_text('changed',encoding='utf-8')
    elif change=='add':(package/'new.py').write_text('added',encoding='utf-8')
    else:(package/'engine.py').unlink()
    with pytest.raises(identity.StaleRuntimeError):identity.runner_identity(runner)

def test_stale_request_does_not_execute_or_mutate_cache():
    called=[];cache={'sentinel':object()};previous=dict(cache)
    run=identity.guarded_execute(lambda req,c:called.append(req),lambda:'new','old')
    assert run({'action':'owned'},cache)['error_type']=='stale_worker'
    assert not called and cache==previous

def test_unchanged_request_preserves_exact_response_and_cache_identity():
    result={'ok':True,'rows':[1,2],'outputs':[]};cache={};seen=[]
    def execute(req,current):seen.append((req,current));return result
    run=identity.guarded_execute(execute,lambda:'same','same');request={'action':'owned'}
    assert run(request,cache) is result and seen==[(request,cache)] and seen[0][1] is cache

@pytest.mark.parametrize('fails',(False,True))
def test_source_change_during_execution_refuses_result(fails):
    current={'value':'same'}
    def execute(req,cache):
        current['value']='new'
        if fails:raise ValueError('owned failure')
        return {'ok':True}
    run=identity.guarded_execute(execute,lambda:current['value'],'same')
    assert run({})['error_type']=='stale_worker'

def test_unrelated_backend_failure_keeps_original_error():
    def fail(req,cache):raise ValueError('owned original')
    run=identity.guarded_execute(fail,lambda:'same','same')
    with pytest.raises(ValueError,match='owned original'):run({})

def test_preloaded_package_error_returns_stale_worker():
    def stale():raise identity.StaleRuntimeError('changed')
    run=identity.guarded_execute(lambda req,cache:None,stale,'same')
    assert run({})['error_type']=='stale_worker'
