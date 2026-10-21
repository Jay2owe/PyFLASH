"""Reference families own their collector state and guard every evidence file."""
from copy import deepcopy
from pathlib import Path
import importlib.util
import py_compile
import os
import sys
import pytest
from PyFLASH import report
from reproducibility import validation_registry as registry

@pytest.mark.parametrize('fails',[False,True])
def test_family_does_not_copy_or_overwrite_caller_records(monkeypatch,tmp_path,fails):
    caller={'active':True,'records':[{'kind':'caller-owned','values':[1,2,3]}],'origins':[None]}
    monkeypatch.setattr(report,'_STATE',caller)
    original=deepcopy(caller)
    def module(name):
        class Validator:
            @staticmethod
            def validate(output):
                assert report._STATE is not caller
                assert report.count()==0
                report.start();report.emit({'kind':'owned-reference-family'})
                if fails:raise RuntimeError('owned comparison failed')
                return [report.collect()]
        return Validator
    monkeypatch.setattr(registry,'import_module',module)
    if fails:
        with pytest.raises(RuntimeError,match='owned comparison failed'):
            registry.validate_family('growth',tmp_path)
    else:
        assert registry.validate_family('growth',tmp_path)==[[{'kind':'owned-reference-family'}]]
    assert report._STATE is caller
    assert caller==original


@pytest.mark.parametrize('fails',[False,True])
def test_family_keeps_stale_retained_bytecode_unchanged_and_restores_policy(monkeypatch,tmp_path,fails):
    source=tmp_path/'reference.py';source.write_text('VALUE = 7\n',encoding='utf-8')
    cached=Path(py_compile.compile(str(source),doraise=True));before=cached.read_bytes()
    source.write_text('VALUE = 9\n',encoding='utf-8');os.utime(source,(2000000000,2000000000))
    monkeypatch.setattr(sys,'dont_write_bytecode',False)
    def module(name):
        class Validator:
            @staticmethod
            def validate(output):
                assert sys.dont_write_bytecode
                spec=importlib.util.spec_from_file_location('owned_archived_reference',source)
                native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
                assert native.VALUE==9
                if fails:raise RuntimeError('retained failed calculation')
                return [{'status':'agree','native_value':native.VALUE}]
        return Validator
    monkeypatch.setattr(registry,'import_module',module)
    if fails:
        with pytest.raises(RuntimeError,match='retained failed calculation'):registry.validate_family('growth',tmp_path)
    else:assert registry.validate_family('growth',tmp_path)==[{'status':'agree','native_value':9}]
    assert cached.read_bytes()==before
    assert sys.dont_write_bytecode is False

def test_source_inventory_includes_noncode_authenticated_evidence(monkeypatch,tmp_path):
    script=Path(__file__).resolve().parents[1]/'scripts/check_reference_family.py'
    spec=importlib.util.spec_from_file_location('owned_reference_guard',script)
    runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
    monkeypatch.setattr(runner,'ROOT',tmp_path)
    fake_script=tmp_path/'scripts/check_reference_family.py'
    fake_script.parent.mkdir();fake_script.write_text('producer')
    monkeypatch.setattr(runner,'__file__',str(fake_script))
    evidence=tmp_path/'reproducibility/reference-sources/owned-native'
    evidence.mkdir(parents=True)
    for name in ('native.log','installed.xml','progress.jsonl','input.csv'):
        (evidence/name).write_text('original accepted evidence')
    before=runner.source_identity()
    for name in ('native.log','installed.xml','progress.jsonl','input.csv'):
        key='reproducibility/reference-sources/owned-native/'+name
        assert key in before
        (evidence/name).write_text('changed evidence')
        assert runner.source_identity()[key]!=before[key]
        (evidence/name).unlink()
        assert key not in runner.source_identity()
