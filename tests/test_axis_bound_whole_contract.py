import json
import shutil
import pytest
from reproducibility import axis_bound_contract as contract

@pytest.mark.parametrize('item',contract.cases(),ids=lambda row:row['key'])
def test_complete_display_bound_matches_unchanged_qualified_profile(item):
    contract.production(item)

def test_original_transport_disagreement_and_qualified_answers_remain_authenticated():
    contract.check_identity()

@pytest.mark.parametrize('damage',['manifest','original','qualification'])
def test_altered_original_or_qualification_cannot_pass(damage,tmp_path,monkeypatch):
    archive=tmp_path/'archive';shutil.copytree(contract.ARCHIVE,archive)
    path=archive/({'manifest':'source-files.json','original':'original/before.json',
        'qualification':'qualified/transport-amendment.json'}[damage])
    path.write_bytes(path.read_bytes()+b' ')
    monkeypatch.setattr(contract,'ARCHIVE',archive)
    with pytest.raises((ValueError,AssertionError)):contract.check_identity()

@pytest.mark.parametrize('damage',['value','type','refusal'])
def test_changed_prediction_cannot_replace_original(damage):
    item=next(row for row in contract.cases() if row['case']['key']=='axis-bound.dtype.int64')
    item['expected']={'value':0,'type':'float'} if damage=='value' else {'value':45.,'type':'int'} if damage=='type' else {'error':'ValueError'}
    with pytest.raises(AssertionError):contract.production(item)

@pytest.mark.parametrize('damage',['value','refusal','ownership'])
def test_wrong_result_admission_or_input_mutation_cannot_pass(damage,monkeypatch):
    from PyFLASH import utils
    if damage=='value':
        item=next(row for row in contract.cases() if row['case']['key']=='axis-bound.dtype.int64')
        monkeypatch.setattr(utils,'round_up_to_nearest_5',lambda value:0)
    elif damage=='refusal':
        item=next(row for row in contract.cases() if row['case']['key']=='axis-bound.domain.text')
        monkeypatch.setattr(utils,'round_up_to_nearest_5',lambda value:1.)
    else:
        item=next(row for row in contract.cases() if row['case']['key']=='axis-bound.domain.array')
        def mutate(value):
            value[0]=31
            raise TypeError('unsupported array')
        monkeypatch.setattr(utils,'round_up_to_nearest_5',mutate)
    with pytest.raises(AssertionError):contract.production(item)

def test_whole_display_policy_requires_previous_answers_and_no_parent_scope():
    assert len(contract.cases())==211
    assert len(contract.required_keys(contract.CAPABILITY))>211
    assert not contract.required_keys('PyFLASH.markers.Antibody.analyse_roi')
    assert not contract.required_keys('PyFLASH.utils.moving_average')

def test_case_predictions_are_caller_owned():
    original=contract.cases();changed=contract.cases();changed[0]['expected'].clear()
    assert contract.cases()==original


def test_inventory_requires_new_and_original_bound_obligations():
    from reproducibility.run import inventory
    keys=contract.required_keys(contract.CAPABILITY)
    rows={row['capability']:row for row in inventory(keys)}
    assert rows[contract.CAPABILITY]['status']=='validated-complete-contract'
    assert rows[contract.CAPABILITY]['kind']=='functional-custom-scalar-display-bound-policy'
    rows={row['capability']:row for row in inventory(keys-{next(iter(keys))})}
    assert rows[contract.CAPABILITY]['status']!='validated-complete-contract'
    assert rows['PyFLASH.utils.moving_average']['status']!='validated-complete-contract'
