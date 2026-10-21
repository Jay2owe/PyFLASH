"""Changing a frozen answer must fail even when original sources still match."""
from pathlib import Path
import importlib,json
import pytest

@pytest.mark.parametrize('name',['variance_student','mann_whitney','print_export'])
def test_changed_current_answer_cannot_hide_behind_an_unchanged_archive(tmp_path,monkeypatch,name):
    contract=importlib.import_module('reproducibility.'+name+'_contract')
    fixture=json.loads(contract.FIXTURE.read_text(encoding='utf-8'))
    fixture['rows'][0]['expected']={'tampered-to-match-a-new-implementation':True}
    changed=tmp_path/'changed.json';changed.write_text(json.dumps(fixture),encoding='utf-8')
    monkeypatch.setattr(contract,'FIXTURE',changed)
    with pytest.raises(ValueError,match='frozen before-correction'):contract.check_identity()

@pytest.mark.parametrize('filename',['annotation_complete_reference.json','stats_cache_complete_reference.json'])
def test_changed_functional_answers_cannot_replace_the_original_declaration(tmp_path,monkeypatch,filename):
    from reproducibility import presentation_cache_contract as contract
    for name in ('annotation_complete_reference.json','stats_cache_complete_reference.json'):
        fixture=json.loads((contract.FIXTURES/name).read_text(encoding='utf-8'))
        if name==filename:fixture['rows'][0]['expected']={'tampered':True}
        (tmp_path/name).write_text(json.dumps(fixture),encoding='utf-8')
    monkeypatch.setattr(contract,'FIXTURES',tmp_path)
    with pytest.raises(ValueError,match='frozen before-correction'):contract.check_identity()
