"""Inherited exposure needs actual subclass calls and its own obligations."""
from copy import deepcopy
from pathlib import Path
import shutil
import pytest
from reproducibility import inherited_mini_metadata_contract as contract

CASES=contract.cases()

@pytest.fixture(scope='module',autouse=True)
def original_evidence_identity():contract.check_identity()

@pytest.mark.parametrize('item',CASES,ids=lambda item:item['key'])
def test_actual_inherited_metadata_matches_original_literal_contract(item,tmp_path):
    before=deepcopy(item);contract.production(item,tmp_path);assert item==before

@pytest.mark.parametrize('name',['run.json','predictions.json','original-experiment_metadata_contract.py',
    'unicode-input-amendment-20261009-v1/inputs.json',
    'unicode-input-amendment-20261009-v1/answers.json'])
def test_changed_inherited_evidence_refuses(name,tmp_path,monkeypatch):
    copied=tmp_path/'evidence';shutil.copytree(contract.ARCHIVE,copied)
    path=copied/name;path.write_bytes(path.read_bytes()+b' ')
    monkeypatch.setattr(contract,'ARCHIVE',copied)
    with pytest.raises(ValueError):contract.check_identity()

def test_wrong_subclass_reporting_cannot_borrow_parent_pass(tmp_path,monkeypatch):
    from PyFLASH.experiment import MiniExperiment
    monkeypatch.setattr(MiniExperiment,'info',lambda self:print('wrong inherited report'))
    item=next(item for item in CASES if item['capability'].endswith('.info'))
    with pytest.raises(AssertionError):contract.production(item,tmp_path)

def test_changed_literal_prediction_refuses(tmp_path):
    item=deepcopy(CASES[0]);item['expected']['invented']=True
    with pytest.raises(AssertionError):contract.production(item,tmp_path)

def test_only_the_five_executed_metadata_exposures_are_complete():
    assert len(CASES)==len({item['key'] for item in CASES})==169
    assert contract.COMPLETE_CAPABILITIES=={item['capability'] for item in CASES}
    for capability in contract.COMPLETE_CAPABILITIES:
        assert contract.required_keys(capability)=={item['key'] for item in CASES if item['capability']==capability}
    assert not contract.required_keys('PyFLASH.experiment.MiniExperiment.processData')

def test_inherited_metadata_inventory_requires_actual_subclass_cases():
    from reproducibility.run import _build_inventory
    metadata=_build_inventory();rows={row['capability']:row for row in metadata['rows']}
    for capability in contract.COMPLETE_CAPABILITIES:
        assert rows[capability]['kind']=='functional-experiment-metadata-and-paths'
        assert set(metadata['required'][capability])==contract.required_keys(capability)


def test_historical_inputs_remain_exact_and_original_unicode_inputs_are_added():
    from reproducibility import experiment_metadata_contract as original
    assert CASES[:145] == contract.read('predictions.json')
    canonical = {row['key']:row for row in original.cases() if row['owner'].startswith('Experiment.')}
    added = CASES[145:]
    assert len(added) == 24
    assert all(item['case'] == canonical[item['case']['key']] for item in added)


@pytest.mark.parametrize('mode',['0','1'])
def test_original_metadata_inputs_are_utf8_in_both_interpreter_modes(mode):
    import json,subprocess,sys
    from reproducibility import experiment_metadata_contract as original
    root=Path(__file__).resolve().parents[1]
    code=f'import sys,json; sys.path.insert(0,{str(root)!r}); from reproducibility.experiment_metadata_contract import cases; print(json.dumps(cases()))'
    result=subprocess.run([sys.executable,'-I','-X','utf8='+mode,'-c',code],
        capture_output=True,text=True,encoding='utf-8',timeout=20)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)==original.cases()
