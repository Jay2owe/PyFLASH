"""Focused reference receipts must fail on changed code or incomplete execution."""
import importlib.util
import json
from pathlib import Path
import pytest
from reproducibility import validation_registry as registry

PATH=Path(__file__).resolve().parents[1]/'scripts/check_reference_family.py'
spec=importlib.util.spec_from_file_location('reference_family_runner',PATH)
runner=importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

def test_registry_dispatches_every_family_once_in_declared_order(tmp_path,monkeypatch):
    calls=[]
    def module(name):
        class Validator:
            @staticmethod
            def validate(output):
                calls.append((name,output))
                return [name]
        return Validator
    monkeypatch.setattr(registry,'import_module',module)
    assert registry.validate_all(tmp_path)==list(registry.FAMILIES.values())
    assert calls==[(module,tmp_path/'reference-family-output'/name) for name,module in registry.FAMILIES.items()]
    with pytest.raises(KeyError):registry.validate_family('unregistered',tmp_path)


def test_full_reference_run_keeps_overlapping_public_case_files_separate(tmp_path,monkeypatch):
    from reproducibility import workflow
    monkeypatch.setattr(workflow,'request',lambda output:None)
    monkeypatch.setattr(registry,'FAMILIES',{'routing':'client.routing','schema':'client.schema'})
    def module(name):
        class Validator:
            @staticmethod
            def validate(output):
                folder=output/'same-public-export-case'
                folder.mkdir(exist_ok=False)
                (folder/'complete-original-answer.json').write_text(name,encoding='utf-8')
                return [{'contract':name,'status':'agree'}]
        return Validator
    monkeypatch.setattr(registry,'import_module',module)
    rows=registry.validate_all(tmp_path)
    assert [row['contract'] for row in rows]==['client.routing','client.schema']
    for name,module_name in registry.FAMILIES.items():
        path=tmp_path/'reference-family-output'/name/'same-public-export-case/complete-original-answer.json'
        assert path.read_text(encoding='utf-8')==module_name
    # Reusing a run owner must preserve original outputs and fail, not overwrite.
    with pytest.raises(registry.ReferenceFamilyFailure):registry.validate_all(tmp_path)
    assert len(rows)==2 and all(row['status']=='agree' for row in rows)

@pytest.mark.parametrize('mode',['agree','disagree','exception','source-added','source-deleted'])
def test_receipt_preserves_evidence_and_refuses_false_success(tmp_path,monkeypatch,mode):
    root=tmp_path/'repository';root.mkdir()
    source=root/'producer.py';source.write_text('original')
    output=tmp_path/'evidence';output.mkdir()
    monkeypatch.setattr(runner,'ROOT',root)
    identities=[{'producer.py':'original-hash'}]
    if mode=='source-added':identities.append({'producer.py':'original-hash','new.py':'new-hash'})
    elif mode=='source-deleted':identities.append({})
    else:identities.append(identities[0])
    monkeypatch.setattr(runner,'source_identity',lambda:identities.pop(0))
    def validate(name,path):
        (path/'partial-journal.json').write_text('{"completed":1}')
        if mode=='exception':raise RuntimeError('reference interrupted')
        return [{'contract':'declared-output','reference':'literal-independent-answer',
                 'status':'disagree' if mode=='disagree' else 'agree'}]
    monkeypatch.setattr(registry,'validate_family',validate)
    receipt=runner.run_family('growth',output)
    assert receipt['passed']==(mode=='agree')
    assert json.loads((output/'run.json').read_text())==receipt
    assert (output/'sources/producer.py').read_text()=='original'
    assert json.loads((output/'partial-journal.json').read_text())=={'completed':1}
    assert 'this family only' in (output/'DIFFERENCES.md').read_text()
    if mode=='exception':assert 'reference interrupted' in receipt['error']
    if mode.startswith('source-'):assert receipt['source_changes_during_run']

def test_source_identity_includes_producer_and_new_deleted_reference_inputs(tmp_path,monkeypatch):
    script=tmp_path/'scripts/check_reference_family.py'
    script.parent.mkdir();script.write_text('producer')
    reference=tmp_path/'reproducibility/fixture.json'
    reference.parent.mkdir();reference.write_text('{}')
    monkeypatch.setattr(runner,'ROOT',tmp_path)
    monkeypatch.setattr(runner,'__file__',str(script))
    before=runner.source_identity()
    reference.unlink()
    replacement=tmp_path/'reproducibility/new.R';replacement.write_text('new')
    after=runner.source_identity()
    assert 'scripts/check_reference_family.py' in before
    assert 'reproducibility/fixture.json' in before and 'reproducibility/fixture.json' not in after
    assert 'reproducibility/new.R' in after
