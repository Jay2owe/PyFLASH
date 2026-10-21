import importlib.util
import shutil
import pytest
from reproducibility import association_fisher_contract as contract

@pytest.mark.parametrize('row',contract.cases(),ids=lambda row:row['key'])
def test_native_sample_size_boundary_through_actual_analysis_and_plot(row):
    contract.check_identity()
    result=contract.production(row)
    assert result['inputs_unchanged'] and result['public_plot_agrees']
    assert not contract.COMPLETE_CAPABILITIES

@pytest.mark.parametrize('name',['source-manifest.json','association-fisher-native-before-20261007-v2/frozen-before.json'])
def test_changed_native_boundary_refuses_before_analysis(tmp_path,monkeypatch,name):
    spec=importlib.util.spec_from_file_location('isolated_fisher_evidence',contract.__file__)
    isolated=importlib.util.module_from_spec(spec);spec.loader.exec_module(isolated)
    archive=tmp_path/'archive';shutil.copytree(contract.ARCHIVE,archive)
    target=archive/name;target.write_bytes(target.read_bytes()+b'\n');isolated.ARCHIVE=archive
    monkeypatch.setattr(isolated,'production',lambda *_:pytest.fail('Changed native evidence reached analysis'))
    with pytest.raises(ValueError,match='evidence'):isolated.validate(tmp_path/'output')
