from copy import deepcopy
import shutil
import pytest
from reproducibility import coloc_annotation_contract as contract
CASES=contract.cases()
@pytest.fixture(scope='module',autouse=True)
def original_evidence():contract.check_identity()
@pytest.mark.parametrize('item',CASES,ids=lambda item:item['key'])
def test_actual_owner_annotation_options(item):
    before=deepcopy(item);contract.production(item);assert item==before
@pytest.mark.parametrize('name',['original-v2/predictions.json','original-v2/original-markers.py','whole-candidate/paired.json'])
def test_changed_annotation_evidence_refuses(name,tmp_path,monkeypatch):
    target=tmp_path/'evidence';shutil.copytree(contract.ARCHIVE,target)
    p=target/name;p.write_bytes(p.read_bytes()+b' ');monkeypatch.setattr(contract,'ARCHIVE',target)
    with pytest.raises(ValueError):contract.check_identity()
@pytest.mark.parametrize('owner',['Antibody','cellMarker','objectMarker'])
def test_damaged_owner_annotation_cannot_borrow_other_owner_proof(owner,monkeypatch):
    from PyFLASH import markers
    monkeypatch.setattr(getattr(markers,owner),'addColocData',lambda self,threshold:self.df)
    item=next(item for item in CASES if item['owner']==owner and item['style']=='volume')
    with pytest.raises(AssertionError):contract.production(item)
def test_changed_annotation_prediction_refuses():
    item=deepcopy(CASES[0]);item['expected']=[9,9,9]
    with pytest.raises(AssertionError):contract.production(item)
def test_only_annotation_owners_are_scoped():
    assert len(CASES)==2205
    assert all(len(contract.required_keys(name))==735 for name in contract.CAPABILITIES)
    assert not contract.required_keys('PyFLASH.markers.Antibody.clean_df')

def test_inventory_requires_every_actual_owner_option():
    from reproducibility.run import _build_inventory
    inventory=_build_inventory()
    for name in contract.CAPABILITIES:
        assert set(inventory['required'][name])==contract.required_keys(name)
        assert len(inventory['required'][name])==735
    assert contract.COMPLETE_CAPABILITIES==contract.CAPABILITIES
