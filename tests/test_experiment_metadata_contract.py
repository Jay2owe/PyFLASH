from pathlib import Path
import importlib.util
import shutil
import pytest
from reproducibility import experiment_metadata_contract as contract
from PyFLASH.experiment import Experiment

@pytest.mark.parametrize('row',contract.cases(),ids=lambda row:row['key'])
def test_complete_literal_metadata_outputs_and_ownership(row,tmp_path):
    contract.check_identity()
    assert contract.production(row,tmp_path)==row['expected']
    assert row['capability'] in contract.CAPABILITIES

@pytest.mark.parametrize('name',['source-manifest.json','experiment-metadata-functional-before-20261006-v2/frozen-before.json'])
def test_changed_metadata_answers_refuse_before_reporting(name,tmp_path,monkeypatch):
    spec=importlib.util.spec_from_file_location('isolated_metadata_guard',contract.__file__)
    isolated=importlib.util.module_from_spec(spec);spec.loader.exec_module(isolated)
    archive=tmp_path/'archive';shutil.copytree(contract.ARCHIVE,archive)
    target=archive/name;target.write_bytes(target.read_bytes()+b'\n')
    isolated.ARCHIVE=archive
    monkeypatch.setattr(isolated,'production',lambda *_:pytest.fail('Changed reference reached production'))
    with pytest.raises(ValueError,match='evidence'):isolated.validate(tmp_path/'output')

def test_wrong_reporting_is_retained_without_hiding_later_cases(tmp_path,monkeypatch):
    monkeypatch.setattr(Experiment,'info',lambda self:print('wrong status'))
    rows=contract.validate(tmp_path)
    assert len(rows)==153
    wrong=[row for row in rows if row['status']=='disagree']
    assert len(wrong)==4 and all(row['contract'].startswith('metadata-info.') for row in wrong)
    assert len({row['contract'] for row in rows})==153
