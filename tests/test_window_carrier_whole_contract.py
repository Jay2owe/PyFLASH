"""Preserve the original represented cells through complete moving windows."""
import copy,shutil
import numpy as np
import pytest
from reproducibility import window_carrier_contract as contract

@pytest.mark.parametrize('item',contract.cases(),ids=lambda row:row['key'])
def test_complete_window_carrier_width_and_admission_profile(item):contract.production(item)

def test_original_failures_native_sources_and_narrow_refusal_amendment_are_authenticated():contract.check_identity()

@pytest.mark.parametrize('damage',['native','original','amendment'])
def test_changed_original_or_qualified_evidence_cannot_pass(damage,tmp_path,monkeypatch):
    archive=tmp_path/'archive';shutil.copytree(contract.ARCHIVE,archive)
    path=archive/({'native':'original/native-source/stats/rv.py','original':'original/run.json',
                   'amendment':'qualified/refusal-class-amendment.json'}[damage])
    path.write_bytes(path.read_bytes()+b' ');monkeypatch.setattr(contract,'ARCHIVE',archive)
    with pytest.raises((AssertionError,ValueError)):contract.check_identity()

@pytest.mark.parametrize('damage',['value','dtype','refusal'])
def test_changed_frozen_prediction_cannot_replace_original(damage):
    item=next(row for row in contract.cases() if row['key']=='window-carrier.ordinary.float64.3')
    if damage=='value':item['expected']['output']['values'][0]={'hex':float(999).hex()}
    elif damage=='dtype':item['expected']['output']['dtype']='object'
    else:item['expected']={'error':'TypeError'}
    with pytest.raises(AssertionError):contract.production(item)

@pytest.mark.parametrize('damage',['lost-small-value','noop-alias','scalar-admission','input-mutation'])
def test_wrong_values_aliases_or_admission_cannot_pass(damage,monkeypatch):
    from PyFLASH import utils
    original=utils.moving_average
    key={'lost-small-value':'window-carrier.tiny.float64.3','noop-alias':'window-carrier.ordinary.float64.1',
         'scalar-admission':'window-carrier.scalar.object.3','input-mutation':'window-carrier.ordinary.float64.3'}[damage]
    item=next(row for row in contract.cases() if row['key']==key)
    def broken(data,width):
        if damage=='scalar-admission':return np.ones(3,dtype=object)
        if damage=='input-mutation':data[0]=999
        result=original(data,width)
        if damage=='lost-small-value':return np.zeros_like(result)
        if damage=='noop-alias':return result.copy()
        return result
    monkeypatch.setattr(utils,'moving_average',broken)
    with pytest.raises(AssertionError):contract.production(item)

def test_all_previous_window_obligations_remain_required_without_parent_promotion():
    assert len(contract.cases())==len({row['key'] for row in contract.cases()})==400
    assert len(contract.required_keys(contract.CAPABILITY))==660
    assert not contract.required_keys('PyFLASH.markers.Antibody.analyse_roi')
    assert not contract.required_keys('PyFLASH.experiment.Experiment.analyse_ventricle')

def test_original_predictions_are_caller_owned():
    before=contract.cases();changed=contract.cases();changed[0]['expected'].clear()
    assert contract.cases()==before

def test_inventory_requires_all_original_and_new_window_obligations():
    from reproducibility.run import inventory
    keys=contract.required_keys(contract.CAPABILITY)
    rows={row['capability']:row for row in inventory(keys)}
    assert rows[contract.CAPABILITY]['status']=='validated-complete-contract'
    rows={row['capability']:row for row in inventory(keys-{next(iter(keys))})}
    assert rows[contract.CAPABILITY]['status']!='validated-complete-contract'
    assert rows['PyFLASH.experiment.Experiment.processData']['status']!='validated-complete-contract'
