import importlib.util
import shutil
import pytest
from reproducibility import dataframe_identifier_contract as contract

@pytest.mark.parametrize('row',contract.cases(),ids=lambda row:row['key'])
def test_exact_identifiers_and_unchanged_measurements_through_public_constructor(row,tmp_path):
    contract.check_identity()
    assert contract.production(row,tmp_path)==row['expected']
    assert not contract.COMPLETE_CAPABILITIES

@pytest.mark.parametrize('name',['source-manifest.json','dataframe-identifiers-functional-before-20261007-v3/frozen-before.json'])
def test_changed_identifier_evidence_refuses_before_constructing_a_table(tmp_path,monkeypatch,name):
    spec=importlib.util.spec_from_file_location('isolated_identifier_evidence',contract.__file__)
    isolated=importlib.util.module_from_spec(spec);spec.loader.exec_module(isolated)
    archive=tmp_path/'archive';shutil.copytree(contract.ARCHIVE,archive)
    target=archive/name;target.write_bytes(target.read_bytes()+b'\n');isolated.ARCHIVE=archive
    monkeypatch.setattr(isolated,'production',lambda *_:pytest.fail('Changed evidence reached a constructor'))
    with pytest.raises(ValueError,match='evidence'):isolated.validate(tmp_path/'output')
