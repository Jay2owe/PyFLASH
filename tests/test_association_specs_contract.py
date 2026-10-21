"""Literal request schemas, stable output labels and one shared validator."""
import pytest
from reproducibility import association_specs_contract as reference

@pytest.mark.parametrize('case',reference.cases(),ids=lambda row:row['key'])
def test_association_request_against_frozen_literal_answer(case):
    assert reference.production(case)==reference.expected(case)

def test_association_reference_identity_and_retained_failures():
    fixture=reference.check_identity()
    assert len(fixture['rows'])==84 and len(fixture['original_failures'])==4

@pytest.mark.parametrize('name',['coefficients','correlations'])
def test_both_association_interfaces_delegate_to_the_same_validator(monkeypatch,name):
    from PyFLASH import association_coefficients,association_correlations,_association_specs
    module=association_coefficients if name=='coefficients' else association_correlations
    calls=[];sentinel=[]
    def shared(request,**options):calls.append((request,options));return sentinel
    monkeypatch.setattr(_association_specs,'normalize_association_specs',shared)
    request=[{'x':'X','y':'Y'}]
    assert module.normalize_specs(request) is sentinel
    assert calls==[(request,{'include_label':name=='correlations'})]

def test_validating_caller_covariates_does_not_mutate_their_inputs():
    from PyFLASH._association_specs import normalize_association_specs
    request={'Study':{'x':'X','y':'Y','covariates':['Age','Sex']}}
    answer=normalize_association_specs(request)
    answer[0]['covariates'].clear()
    assert request=={'Study':{'x':'X','y':'Y','covariates':['Age','Sex']}}
