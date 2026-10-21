"""Each inherited boundary exposure owns every call and its saved proof."""
from copy import deepcopy
import shutil
import pytest
from reproducibility import inherited_roi_contract as contract
CASES=contract.cases()

@pytest.fixture(scope='module',autouse=True)
def original_evidence_identity():contract.check_identity()

@pytest.mark.parametrize('item',CASES,ids=lambda item:item['key'])
def test_actual_subclass_boundary_and_saved_carrier(item,tmp_path):
    before=deepcopy(item);contract.production(item,tmp_path);assert item==before

@pytest.mark.parametrize('name',['run.json','predictions.json','original-inherited_roi_reference_adapter.py'])
def test_altered_original_boundary_evidence_refuses(name,tmp_path,monkeypatch):
    target=tmp_path/'evidence';shutil.copytree(contract.ARCHIVE,target)
    path=target/name;path.write_bytes(path.read_bytes()+b' ')
    monkeypatch.setattr(contract,'ARCHIVE',target)
    with pytest.raises(ValueError):contract.check_identity()

@pytest.mark.parametrize('owner',['objectMarker','cellMarker'])
def test_damaged_subclass_cannot_borrow_parent_boundary_proof(owner,tmp_path,monkeypatch):
    from PyFLASH import markers
    monkeypatch.setattr(getattr(markers,owner),'analyse_roi',lambda *args,**kwargs:None)
    item=next(row for row in CASES if row['owner']==owner and 'case' in row)
    with pytest.raises(AssertionError):contract.production(item,tmp_path)

def test_changed_boundary_prediction_refuses(tmp_path):
    item=deepcopy(CASES[0]);item['case']['expected']={'distances':[999.]}
    with pytest.raises(AssertionError):contract.production(item,tmp_path)

def test_whole_scope_is_only_two_actually_called_subclass_methods():
    assert len(CASES)==934
    assert contract.COMPLETE_CAPABILITIES=={item['capability'] for item in CASES}
    assert not contract.required_keys('PyFLASH.markers.Antibody.analyse_roi')
    assert not contract.required_keys('PyFLASH.markers.cellMarker.clean_df')

def test_inventory_requires_each_actual_call_and_own_saved_carrier():
    from reproducibility.run import _build_inventory
    metadata=_build_inventory()
    for capability in contract.COMPLETE_CAPABILITIES:
        required=set(metadata['required'][capability])
        assert required==contract.required_keys(capability) and len(required)==467
        assert any(key.endswith('.saved-preview-reproduction') for key in required)


def test_parsed_boundary_evidence_keeps_archive_paths_separate(tmp_path,monkeypatch):
    from reproducibility import roi_analysis_contract as original
    first=tmp_path/'first';second=tmp_path/'second';first.mkdir();second.mkdir()
    (first/'value.json').write_text('{"original":1}')
    (second/'value.json').write_text('{"original":2}')
    monkeypatch.setattr(original,'ARCHIVE',first)
    assert original.read('value.json')=={'original':1}
    monkeypatch.setattr(original,'ARCHIVE',second)
    assert original.read('value.json')=={'original':2}


def test_cached_boundary_values_cannot_hide_altered_evidence(tmp_path,monkeypatch):
    from reproducibility import roi_analysis_contract as original
    target=tmp_path/'evidence';shutil.copytree(original.ARCHIVE,target)
    monkeypatch.setattr(original,'ARCHIVE',target)
    original.check_identity();original.read('native/before.json')
    path=target/'native/before.json';path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError,match='Retained evidence changed: native/before.json'):
        original.check_identity()
