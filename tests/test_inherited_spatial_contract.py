"""Subclass spatial exposure requires actual calls and its own native obligations."""
from copy import deepcopy
import shutil
import pytest
from reproducibility import inherited_spatial_contract as contract

CASES=contract.cases()

@pytest.fixture(scope='module',autouse=True)
def original_evidence_identity():contract.check_identity()

@pytest.mark.parametrize('item',CASES,ids=lambda item:item['key'])
def test_actual_inherited_spatial_consumer_matches_original_native_arrays(item):
    before=deepcopy(item);contract.production(item);assert item==before

@pytest.mark.parametrize('name',['predictions.json','run.json','original-marker_nearest_contract.py'])
def test_changed_inherited_evidence_refuses(name,tmp_path,monkeypatch):
    # Only the changed file and original manifest are needed to prove refusal.
    target=tmp_path/'evidence';target.mkdir()
    for source in contract.ARCHIVE.iterdir():
        if source.name==name or source.name=='source-files.json':shutil.copyfile(source,target/source.name)
    path=target/name;path.write_bytes(path.read_bytes()+b' ')
    monkeypatch.setattr(contract,'ARCHIVE',target)
    with pytest.raises(ValueError):contract.check_identity()

@pytest.mark.parametrize('owner',['objectMarker','cellMarker'])
def test_wrong_subclass_cannot_borrow_parent_nearest_pass(owner,monkeypatch):
    from PyFLASH import markers
    monkeypatch.setattr(getattr(markers,owner),'find_closest_distances_between_markers',lambda self,other:self.df)
    item=next(item for item in CASES if item['kind']=='nearest' and item['owner']==owner and len(item['case']['case']['left'])>0)
    with pytest.raises((AssertionError,KeyError)):contract.production(item)

def test_wrong_lightweight_parent_cannot_borrow_parent_nearest_pass(monkeypatch):
    from PyFLASH.experiment import MiniExperiment
    monkeypatch.setattr(MiniExperiment,'addClosestDistances',lambda self,**kwargs:None)
    item=next(item for item in CASES if item['kind']=='parent-nearest' and len(item['case']['specification']['markers'])>1)
    with pytest.raises((AssertionError,KeyError,AttributeError)):contract.production(item)

def test_changed_prediction_refuses():
    item=deepcopy(CASES[0]);item['target']='wrong-class'
    with pytest.raises(AssertionError):contract.production(item)

def test_only_six_actually_executed_inherited_exposures_are_complete():
    assert len(CASES)==2744
    assert contract.COMPLETE_CAPABILITIES=={item['capability'] for item in CASES}
    assert len(contract.COMPLETE_CAPABILITIES)==6
    assert not contract.required_keys('PyFLASH.markers.objectMarker.analyse_roi')
    assert not contract.required_keys('PyFLASH.experiment.MiniExperiment.importCSVs')

def test_inventory_requires_own_inherited_native_and_corroboration_cases():
    from reproducibility.run import _build_inventory
    metadata=_build_inventory()
    for capability in contract.COMPLETE_CAPABILITIES:
        assert set(metadata['required'][capability])==contract.required_keys(capability)
        assert contract.required_keys(capability)
