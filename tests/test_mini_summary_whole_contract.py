"""Full flat-summary calls cannot pass with missing factors or stale state."""
from copy import deepcopy
import shutil
import pytest
from reproducibility import mini_summary_whole_contract as contract

CASES=contract.cases()

@pytest.fixture(scope='module',autouse=True)
def original_whole_summary_evidence():contract.check_identity()

@pytest.mark.parametrize('item',CASES,ids=lambda item:item['key'])
def test_complete_flat_summary_tables_and_lifecycle_state(item,tmp_path):
    before=deepcopy(item);contract.production(item,tmp_path/'inputs');assert item==before

@pytest.mark.parametrize('name',['original/run.json','late-qualified/before.json','mixed/predictions.json','mixed/native/whole-mini-mixed-factors-results.json','mini_shared_adapter_amendment_20261008_v3.json'])
def test_changed_original_failure_native_answer_or_amendment_refuses(name,tmp_path,monkeypatch):
    copied=tmp_path/'evidence';shutil.copytree(contract.ARCHIVE,copied)
    path=copied/name;path.write_bytes(path.read_bytes()+b' ');monkeypatch.setattr(contract,'ARCHIVE',copied)
    with pytest.raises((ValueError,AssertionError)):contract.check_identity()

@pytest.mark.parametrize('damage',['cell','column','refusal'])
def test_changed_frozen_full_table_prediction_refuses(damage,tmp_path):
    item=next(deepcopy(item) for item in CASES if item['case']['tables']==2 and not item['case']['conflict'] and not item['case'].get('late_first') and not item['case'].get('mixed_codes'))
    if damage=='cell':item['expected']['before']['rows'][0][1]=999
    elif damage=='column':item['expected']['before']['columns'][-1]='Wrong condition'
    else:item['expected']={'error':'TypeError'}
    with pytest.raises(AssertionError):contract.production(item,tmp_path/'inputs')

@pytest.mark.parametrize('damage',['factor','mean','alias'])
def test_wrong_installed_values_factors_or_return_alias_cannot_pass(damage,tmp_path,monkeypatch):
    from PyFLASH.experiment import MiniExperiment
    original=MiniExperiment.createSummary
    def broken(self,progress=True):
        result=original(self,progress=progress)
        if damage=='factor':result['Treatment']='Wrong factor'
        elif damage=='mean':result['Amount1']=999.
        else:return result.copy(deep=True)
        return result
    monkeypatch.setattr(MiniExperiment,'createSummary',broken)
    item=next(item for item in CASES if item['case']['tables']==2 and item['case']['route']=='steps' and not item['case']['conflict'])
    with pytest.raises(AssertionError):contract.production(item,tmp_path/'inputs')

@pytest.mark.parametrize('progress',[False,True])
def test_conflicting_factors_preserve_existing_summary_and_raw_table_identities(tmp_path,progress):
    import pandas as pd
    from PyFLASH.experiment import MiniExperiment
    from PyFLASH.markers import Attribute
    experiment=MiniExperiment('Stored conflict state',str(tmp_path),factor_mappings={'Treatment':{'001':'Control','002':'Treated'}})
    previous=pd.DataFrame({'AnimalName':['Old'],'Treatment':['Control'],'Amount1':[7.]});previous.attrs={'original':[1,2]}
    other=previous.copy(deep=True);experiment.summaries={'SCN':previous,'other':other}
    mapping=experiment.summaries;frames={name:frame.copy(deep=True) for name,frame in mapping.items()}
    for name,treatment in [('First','001'),('Second','002')]:
        experiment.data[name]=Attribute(name,pd.DataFrame({'AnimalName':['A1'],'Treatment':[treatment],name:[3.]}),experiment)
    raw={name:carrier.df for name,carrier in experiment.data.items()};snapshots={name:frame.copy(deep=True) for name,frame in raw.items()}
    with pytest.raises(ValueError,match='conflicting'):experiment.createSummary(progress=progress)
    assert experiment.summaries is mapping and experiment.summary is previous and experiment.summaries['other'] is other
    for name,frame in mapping.items():pd.testing.assert_frame_equal(frame,frames[name],check_exact=True)
    for name,frame in raw.items():
        assert experiment.data[name].df is frame
        pd.testing.assert_frame_equal(frame,snapshots[name],check_exact=True)

def test_only_whole_summary_is_complete_and_all_earlier_numeric_routes_remain_required():
    assert len(CASES)==len({item['key'] for item in CASES})==640
    assert contract.COMPLETE_CAPABILITIES=={contract.CAPABILITY}
    keys=contract.required_keys(contract.CAPABILITY)
    assert {item['key'] for item in CASES}<=keys
    assert any(key.startswith('mini-scientific.integer-boundary.') for key in keys)
    assert any(key.startswith('mini-object-means.') for key in keys)
    assert any(key.startswith('mini-nonfinite-scores.') for key in keys)
    assert not contract.required_keys('PyFLASH.experiment.MiniExperiment.processData')

def test_missing_one_original_obligation_cannot_complete_summary_inventory():
    from reproducibility.run import inventory
    keys=contract.required_keys(contract.CAPABILITY)
    rows={row['capability']:row for row in inventory(keys)}
    assert rows[contract.CAPABILITY]['status']=='validated-complete-contract'
    rows={row['capability']:row for row in inventory(keys-{next(iter(keys))})}
    assert rows[contract.CAPABILITY]['status']!='validated-complete-contract'
    assert rows['PyFLASH.experiment.MiniExperiment.processData']['status']!='validated-complete-contract'
