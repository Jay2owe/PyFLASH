"""Preserve acquired ROI selection without condition metadata."""
import shutil
import pytest
from reproducibility import marker_factor_region_contract as M
from reproducibility import marker_region_contract as Original

@pytest.fixture(scope='module',autouse=True)
def native_before_public_calls(tmp_path_factory):
    M.check_identity();Original.check_native_references(tmp_path_factory.mktemp('factor-only-native'))

@pytest.mark.parametrize('item',M.cases(),ids=lambda item:item['key'])
def test_all_original_factor_only_region_requests(item,tmp_path):
    actual=M.production(item,tmp_path)
    assert actual['caller_tables_unchanged']

@pytest.mark.parametrize('name',['source-manifest.json','factor-only-multi-region-before-20261007-v4/run.json'])
def test_changed_original_factor_metadata_refuses(name,tmp_path,monkeypatch):
    archive=tmp_path/'archive';shutil.copytree(M.ARCHIVE,archive)
    path=archive/name;path.write_bytes(path.read_bytes()+b' ')
    monkeypatch.setattr(M,'ARCHIVE',archive)
    with pytest.raises(ValueError):M.check_identity()

@pytest.mark.parametrize('damage',['n','coordinates'])
def test_wrong_region_scientific_output_cannot_pass(damage,tmp_path):
    item=M.cases()[0];actual=M.production(item,tmp_path)
    if damage=='n':actual['returned']['n'][0]+=1
    else:actual['records'][0]['lines'][0]['x'][1]+=1
    with pytest.raises(AssertionError):Original.check_result(item,actual)
