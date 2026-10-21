from pathlib import Path
import importlib.util
import json
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PyFLASH.dataframe import DataFrameExperiment
import pytest

MODULE=ROOT/'reproducibility/dataframe_lifecycle_contract.py'
@pytest.fixture
def contract():
 spec=importlib.util.spec_from_file_location('staged_dataframe_lifecycle',MODULE)
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 return module

def test_complete_direct_functional_envelope(contract,tmp_path):
 rows=contract.validate(tmp_path)
 assert len(rows)==35 and len({row['contract'] for row in rows})==35
 assert all(row['status']=='agree' for row in rows)
 assert contract.COMPLETE_CAPABILITIES==frozenset('PyFLASH.dataframe.DataFrameExperiment.'+name
  for name in ('getRegionDict','processData','createSavePaths','set_condition_list'))
 paired=json.loads((tmp_path/'dataframe-lifecycle-paired.json').read_text())['rows']
 assert all(row['scientific_vote'] is False and row['kind']=='functional-interface-control' for row in paired)

@pytest.mark.parametrize('manifest',[True,False])
def test_evidence_tampering_refuses_before_public_call(contract,tmp_path,monkeypatch,manifest):
 archive=tmp_path/'archive';shutil.copytree(contract.ARCHIVE,archive)
 path=archive/('source-manifest.json' if manifest else 'dataframe-lifecycle-functional-before-20261006-v3/frozen-before.json')
 path.write_text(path.read_text()+'\n')
 monkeypatch.setattr(contract,'ARCHIVE',archive)
 monkeypatch.setattr(DataFrameExperiment,'getRegionDict',lambda *_:pytest.fail('Changed fixture reached production'))
 with pytest.raises(ValueError,match='evidence'):contract.validate(tmp_path/'output')

@pytest.mark.parametrize('owner',['getRegionDict','processData','createSavePaths','set_condition_list'])
def test_wrong_ownership_fails_every_affected_public_owner(contract,tmp_path,monkeypatch,owner):
 original=getattr(DataFrameExperiment,owner)
 def detached(self,*args,**kwargs):
  result=original(self,*args,**kwargs)
  return dict(result) if isinstance(result,dict) else object()
 monkeypatch.setattr(DataFrameExperiment,owner,detached)
 rows=contract.validate(tmp_path)
 keys=contract.required_keys('PyFLASH.dataframe.DataFrameExperiment.'+owner)
 selected=[row for row in rows if row['contract'] in keys]
 assert any(row['status']=='disagree' for row in selected)
 assert all(row['status']=='agree' for row in rows if row['contract'] not in keys)

def test_first_error_retains_later_comparisons(contract,tmp_path,monkeypatch):
 original=DataFrameExperiment.getRegionDict;calls=[]
 def fail_once(self,*args,**kwargs):
  calls.append(True)
  if len(calls)==1:raise RuntimeError('retained-lifecycle-failure')
  return original(self,*args,**kwargs)
 monkeypatch.setattr(DataFrameExperiment,'getRegionDict',fail_once)
 rows=contract.validate(tmp_path)
 assert len(rows)==35 and rows[0]['status']=='disagree'
 assert all(row['status']=='agree' for row in rows[1:])
 paired=json.loads((tmp_path/'dataframe-lifecycle-paired.json').read_text())['rows']
 assert 'retained-lifecycle-failure' in paired[0]['error']

def test_processing_cannot_change_an_unrelated_field(contract,tmp_path,monkeypatch):
 original=DataFrameExperiment.processData
 def corrupt(self,*args,**kwargs):
  returned=original(self,*args,**kwargs);self.aliases={};return returned
 monkeypatch.setattr(DataFrameExperiment,'processData',corrupt)
 rows=contract.validate(tmp_path)
 keys=contract.required_keys('PyFLASH.dataframe.DataFrameExperiment.processData')
 assert all(row['status']=='disagree' for row in rows if row['contract'] in keys)
