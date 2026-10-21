import copy,json,shutil
import numpy as np
import pytest
from reproducibility import trace_policy_contract as contract

@pytest.mark.parametrize('item',contract.cases(),ids=lambda row:row['key'])
def test_complete_custom_trace_profiles_preserve_every_output_and_input(item):
    contract.production(item)

def test_original_native_arrays_carriers_and_interrupted_preflight_are_authenticated():
    contract.check_identity()

@pytest.mark.parametrize('damage',['manifest','native','profile'])
def test_changed_evidence_cannot_pass(damage,tmp_path,monkeypatch):
    archive=tmp_path/'archive';shutil.copytree(contract.ARCHIVE,archive)
    path=archive/({'manifest':'source-files.json','native':'dense/native/dense-downward-trace-results.json',
                  'profile':'carriers/before.json'}[damage])
    path.write_bytes(path.read_bytes()+b' ')
    monkeypatch.setattr(contract,'ARCHIVE',archive)
    with pytest.raises((ValueError,AssertionError)):contract.check_identity()

@pytest.mark.parametrize('damage',['coordinate','dtype','index'])
def test_changed_frozen_prediction_cannot_replace_original(damage):
    item=next(row for row in contract.cases() if row['group']=='carriers' and row['row']['case']['key']=='trace-profile.ordinary.int64')
    field={'coordinate':'selected_x','dtype':'x_dtype','index':'indices'}[damage]
    item['row']['expected'][field]='incorrect' if damage=='dtype' else [999]
    with pytest.raises(AssertionError):contract.production(item)

@pytest.mark.parametrize('damage',['coordinate','index','dtype','return-alias','refusal-mutation'])
def test_wrong_actual_values_types_or_ownership_cannot_pass(damage,monkeypatch):
    from PyFLASH import utils
    method=utils.trace_downward_nearest
    key='trace-profile.refusal.length.array' if damage=='refusal-mutation' else 'trace-profile.slope-boundary.int64'
    item=next(row for row in contract.cases() if row['group']=='carriers' and row['row']['case']['key']==key)
    def broken(x,y):
        if damage=='refusal-mutation':
            x[0]=999
            raise ValueError('paired finite')
        a,b,indices=method(x,y)
        if damage=='coordinate':a[0]+=1
        elif damage=='index':indices[0]=1
        elif damage=='dtype':a=a.astype(float)
        elif damage=='return-alias':a=x[:len(a)]
        return a,b,indices
    monkeypatch.setattr(utils,'trace_downward_nearest',broken)
    with pytest.raises(AssertionError):contract.production(item)

def test_trace_obligations_require_legacy_answers_without_promoting_boundary_parents():
    assert len(contract.cases())==len({row['key'] for row in contract.cases()})==291
    assert len(contract.required_keys(contract.CAPABILITY))>291
    assert not contract.required_keys('PyFLASH.markers.Antibody.analyse_roi')
    assert not contract.required_keys('PyFLASH.utils.moving_average')

def test_trace_case_and_native_coordinate_lists_are_caller_owned():
    original=contract.cases();changed=contract.cases();changed[0]['row']['expected'].clear()
    assert contract.cases()==original


def test_inventory_requires_new_and_original_trace_obligations():
    from reproducibility.run import inventory
    keys=contract.required_keys(contract.CAPABILITY)
    rows={row['capability']:row for row in inventory(keys)}
    assert rows[contract.CAPABILITY]['status']=='validated-complete-contract'
    assert rows[contract.CAPABILITY]['kind']=='functional-custom-whole-downward-trace-policy'
    rows={row['capability']:row for row in inventory(keys-{next(iter(keys))})}
    assert rows[contract.CAPABILITY]['status']!='validated-complete-contract'
    assert rows['PyFLASH.experiment.Experiment.processData']['status']!='validated-complete-contract'
