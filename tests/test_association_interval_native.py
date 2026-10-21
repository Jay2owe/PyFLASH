from pathlib import Path
import importlib.util
import shutil
import pytest
from reproducibility import association_interval_contract as contract

@pytest.mark.parametrize('row',contract.cases(),ids=lambda row:row['key'])
def test_native_original_value_intervals_across_both_interfaces(row):
    contract.check_identity()
    result=contract.production(row)
    assert result['inputs_unchanged'] and result['other_fields_unchanged']
    assert result['analysis_fields'] and result['public_plot_fields']
    assert not contract.COMPLETE_CAPABILITIES

@pytest.mark.parametrize('name',['source-manifest.json','association-interval-native-before-20261007-v1/frozen-before.json',
                                'narrow-amendment-manifest.json','association-interval-native-before-20261007-v2/frozen-before.json'])
def test_changed_native_intervals_refuse_before_any_analysis(tmp_path,monkeypatch,name):
    spec=importlib.util.spec_from_file_location('isolated_interval_guard',contract.__file__)
    isolated=importlib.util.module_from_spec(spec);spec.loader.exec_module(isolated)
    archive=tmp_path/'archive';shutil.copytree(contract.ARCHIVE,archive)
    target=archive/name;target.write_bytes(target.read_bytes()+b'\n');isolated.ARCHIVE=archive
    monkeypatch.setattr(isolated,'production',lambda *_:pytest.fail('Altered native answer reached analysis'))
    with pytest.raises(ValueError,match='evidence'):isolated.validate(tmp_path/'output')
