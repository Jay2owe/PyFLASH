"""Complete candidate scores, parameter uncertainty, predictions and invalid domains."""
import numpy as np
import pytest
from PyFLASH.stats_extra import fit_growth_curve
from reproducibility import growth_contract as reference

@pytest.mark.parametrize('case',reference.cases(),ids=lambda row:row['key'])
def test_complete_growth_model_against_independently_frozen_answers(case):
    expected=reference.expected(case);actual=reference.production(case)
    assert reference.equal(actual,expected)
    if 'error_type' in expected:
        return
    assert list(actual['params'])==list(expected['params'])
    assert list(actual['all_models'])==list(expected['all_models'])

def test_growth_reference_identity_and_preserved_failures():
    fixture=reference.check_identity()
    assert len(fixture['rows'])==86 and len(fixture['original_failures'])==24

def test_previous_growth_answers_are_preserved():
    import hashlib,json
    previous=reference.FIXTURE.with_name('growth_reference_v3.json')
    original=json.loads(previous.read_text(encoding='utf-8'))
    current=reference.check_identity()
    assert hashlib.sha256(previous.read_bytes()).hexdigest()==current['previous_fixture_sha256']
    assert current['rows'][:len(original['rows'])]==original['rows']

@pytest.mark.parametrize('model',[None,True,42,[],{},'unknown'])
def test_growth_model_names_fail_clearly(model):
    with pytest.raises(ValueError):fit_growth_curve([1,2,3],[2,4,5],model)

@pytest.mark.parametrize('model',['linear','exponential','logistic','auto'])
@pytest.mark.parametrize('x,y',[([],[]),([1],[2]),([1,2],[2,3]),([1,2,3],[2,np.nan,np.inf])])
def test_growth_needs_three_retained_finite_pairs(model,x,y):
    with pytest.raises(ValueError):fit_growth_curve(x,y,model)

def test_growth_does_not_hide_resource_failure(monkeypatch):
    import scipy.optimize
    def exhausted(*args,**kwargs):raise MemoryError('resource failure')
    monkeypatch.setattr(scipy.optimize,'curve_fit',exhausted)
    with pytest.raises(MemoryError):fit_growth_curve([1,2,3,4,5],[1,2,4,8,16],'exponential')

@pytest.mark.parametrize('model',['linear','exponential','logistic','auto'])
@pytest.mark.parametrize('x,y',[(1,2),([[1,2],[3,4]],[[2,3],[4,5]]),([1,2,3],[1,2])])
def test_growth_requires_one_dimensional_paired_inputs(model,x,y):
    with pytest.raises(ValueError):fit_growth_curve(x,y,model)

@pytest.mark.parametrize('model',['linear','exponential','logistic','auto'])
def test_parameters_are_not_reported_when_measurement_times_cannot_identify_them(model):
    with pytest.raises(RuntimeError):fit_growth_curve([1]*8,list(range(8)),model)

@pytest.mark.parametrize('model',['exponential','logistic'])
@pytest.mark.parametrize('x,y',[(list(range(1,9)),[3]*8),([1,1,1,1,2,2,2,2],[1,2,1,2,3,4,3,4])])
def test_nonlinear_models_do_not_report_arbitrary_unidentified_parameters(model,x,y):
    with pytest.raises(RuntimeError):fit_growth_curve(x,y,model)

def test_automatic_constant_signal_uses_identifiable_straight_line_and_exact_zero_residual():
    answer=fit_growth_curve(list(range(1,9)),[3]*8)
    assert answer['model']=='linear' and list(answer['all_models'])==['linear']
    assert answer['params']=={'slope':{'value':0.0,'stderr':0.0},'intercept':{'value':3.0,'stderr':0.0}}
    assert np.isnan(answer['r_squared']) and answer['aic']==-np.inf

def test_changed_candidate_score_breaks_the_full_automatic_contract():
    case=next(c for c in reference.cases() if c['parameters']['model']=='auto')
    expected=reference.expected(case);changed=reference.expected(case)
    candidate=next(iter(changed['all_models']));changed['all_models'][candidate]['aic']+=.01
    assert not reference.equal(changed,expected)
