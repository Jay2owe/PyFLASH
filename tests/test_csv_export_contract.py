import importlib.util
import shutil
import pytest
from reproducibility import csv_export_contract as contract

@pytest.mark.parametrize('row',contract.cases(),ids=lambda row:row['key'])
def test_complete_literal_files_and_caller_ownership(row,tmp_path):
    contract.check_identity()
    assert contract.production(row,tmp_path)=={'files':row['expected_files'],'inputs_unchanged':True,'returned_none':True}

@pytest.mark.parametrize('name',['source-manifest.json','csv-export-functional-before-20261007-v2/frozen-before.json'])
def test_changed_csv_evidence_refuses_before_export(tmp_path,monkeypatch,name):
    spec=importlib.util.spec_from_file_location('isolated_csv_evidence',contract.__file__)
    isolated=importlib.util.module_from_spec(spec);spec.loader.exec_module(isolated)
    archive=tmp_path/'archive';shutil.copytree(contract.ARCHIVE,archive)
    target=archive/name;target.write_bytes(target.read_bytes()+b'\n');isolated.ARCHIVE=archive
    monkeypatch.setattr(isolated,'production',lambda *_:pytest.fail('Changed evidence reached export'))
    with pytest.raises(ValueError,match='evidence'):isolated.validate(tmp_path/'output')
