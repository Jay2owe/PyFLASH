"""Inherited serialization needs actual subclass calls and independent file reads."""
from copy import deepcopy
import shutil
import pytest
from reproducibility import inherited_mini_csv_contract as contract
CASES=contract.cases()

@pytest.fixture(scope='module',autouse=True)
def original_evidence_identity():contract.check_identity()

@pytest.mark.parametrize('item',CASES,ids=lambda item:item['key'])
def test_actual_inherited_csv_matches_every_original_file_cell(item,tmp_path):
    before=deepcopy(item);contract.production(item,tmp_path);assert item==before

@pytest.mark.parametrize('name',['run.json','predictions.json','original-csv_export_contract.py'])
def test_changed_inherited_csv_evidence_refuses(name,tmp_path,monkeypatch):
    target=tmp_path/'evidence';shutil.copytree(contract.ARCHIVE,target)
    path=target/name;path.write_bytes(path.read_bytes()+b' ')
    monkeypatch.setattr(contract,'ARCHIVE',target)
    with pytest.raises(ValueError):contract.check_identity()

@pytest.mark.parametrize('method',['save_csvs','save_column_csvs','save_attribute_csvs'])
def test_wrong_subclass_export_cannot_borrow_parent_pass(method,tmp_path,monkeypatch):
    from PyFLASH.experiment import MiniExperiment
    monkeypatch.setattr(MiniExperiment,method,lambda self:None)
    item=next(item for item in CASES if item['capability'].endswith('.'+method) and item['expected']['files'])
    with pytest.raises(AssertionError):contract.production(item,tmp_path)

def test_changed_csv_prediction_refuses(tmp_path):
    item=deepcopy(CASES[0]);item['expected']['returned_none']=False
    with pytest.raises(AssertionError):contract.production(item,tmp_path)

def test_only_three_actually_executed_csv_exposures_are_complete():
    assert len(CASES)==15
    assert contract.COMPLETE_CAPABILITIES=={item['capability'] for item in CASES}
    assert not contract.required_keys('PyFLASH.experiment.MiniExperiment.importCSVs')

def test_inventory_requires_actual_inherited_csv_cases():
    from reproducibility.run import _build_inventory
    metadata=_build_inventory();rows={row['capability']:row for row in metadata['rows']}
    for capability in contract.COMPLETE_CAPABILITIES:
        assert set(metadata['required'][capability])==contract.required_keys(capability)
        assert rows[capability]['kind']=='functional-csv-serialization-and-batch-destinations'
