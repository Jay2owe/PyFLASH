"""Complete covariance-adjusted reports, preflight, small error and lineage."""
from copy import deepcopy
import json
import pytest
from reproducibility import linear_model_contract as contract

@pytest.mark.parametrize('case',contract.cases(),ids=lambda row:row['key'])
def test_every_model_report_field_matches_independent_answer(case):
    original=deepcopy(case)
    assert contract.equal(contract.production(case),case['expected'])
    assert case==original

def test_original_model_failures_and_answers_are_retained():
    fixture=contract.check_identity()
    assert len(fixture['rows'])==295
    assert sum(row['original_failure'] for row in fixture['rows'])==227

def test_invalid_model_request_precedes_fitting_and_report_mutation(monkeypatch):
    import pandas as pd
    from PyFLASH import stats
    case=next(c for c in contract.cases() if c['key']=='linear-model.complete.0')
    def forbidden(*args,**kwargs):raise AssertionError('Fitting preceded request validation')
    monkeypatch.setattr(stats,'_dependency',forbidden)
    for options in ({'comparisons':['0-2']},{'comparisons':['1-1']},{'posthoc_correction':'made-up'},
                    {'covariates':['missing']},{'group_order':['A','A','C']},{'cov_type':'HC3','cov_kwds':{'use_t':'yes'}}):
        raw={'caller':'retained'};parameters=deepcopy(case['parameters']);parameters.update(options)
        with pytest.raises(ValueError):stats.runLinearModel(pd.DataFrame(case['data']),results_dict=raw,**parameters)
        assert raw=={'caller':'retained'}

def test_full_model_parent_requires_every_report_and_published_matrix():
    from reproducibility.run import inventory
    from reproducibility.linear_model_validation import required_keys
    keys=required_keys();capability='PyFLASH.stats.runLinearModel'
    assert next(r for r in inventory(keys) if r['capability']==capability)['status']=='validated-complete-contract'
    for missing in ('linear-model.complete.0','linear-model.boundary.0','linear-model.degenerate.0','linear-native.HC3'):
        assert next(r for r in inventory(keys-{missing}) if r['capability']==capability)['status']!='validated-complete-contract'

def test_tampering_with_an_original_model_answer_fails_identity(monkeypatch,tmp_path):
    payload=json.loads(contract.FIXTURE.read_text());payload['rows'][0]['expected']['method']='Changed'
    changed=tmp_path/'changed.json';changed.write_text(json.dumps(payload));monkeypatch.setattr(contract,'FIXTURE',changed)
    with pytest.raises(ValueError,match='differ from frozen'):contract.check_identity()
