"""Missing, duplicated, undefined and disagreeing evidence cannot qualify outlier parents."""
from copy import deepcopy
import pytest
from reproducibility import outlier_whole_contract as contract


def healthy():
    return [dict(contract=key,status='agree',frozen_reference_agrees=True,missingness_equal=True)
            for f in contract.declaration()['families'] for key in f['keys']]


def test_all_arguments_and_566_parent_obligations_are_declared():
    d=contract.declaration()
    assert len(d['covered_parameters'])==27
    assert sum(len(v) for v in d['required'].values())==566
    result=contract.coverage(healthy())
    assert result['passed'] and result['observed_cases']==576 and all(result['methods'].values())
    assert not result['whole_package_approval']


@pytest.mark.parametrize('fault',['missing','duplicate','disagree','changed-reference','undefined','unknown'])
def test_incomplete_or_invalid_evidence_cannot_pass(fault):
    rows=deepcopy(healthy())
    if fault=='missing':rows.pop()
    elif fault=='duplicate':rows.append(rows[0])
    elif fault=='disagree':rows[0]['status']='disagree'
    elif fault=='changed-reference':rows[0]['frozen_reference_agrees']=False
    elif fault=='undefined':rows[0]['missingness_equal']=False
    else:rows.append(dict(contract='outlier-options.undeclared',status='agree',frozen_reference_agrees=True,missingness_equal=True))
    assert not contract.coverage(rows)['passed']
