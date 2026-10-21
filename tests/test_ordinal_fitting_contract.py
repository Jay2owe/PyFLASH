"""Lock complete native fits and refuse unstable or invalid refinements."""
from copy import deepcopy
from fractions import Fraction
import json
import numpy as np
import pytest
from scipy import optimize,sparse
from reproducibility import ordinal_fitting_contract as contract


@pytest.mark.parametrize('row',contract.cases(),ids=lambda row:row['case']['key'])
def test_complete_fitted_state_and_responses_match_unchanged_native_answers(row):
    original=deepcopy(row)
    assert contract.equal(contract.observe(row['case']),row['expected'])
    assert row==original


@pytest.mark.parametrize('row',contract.cases()[:48],ids=lambda row:row['case']['key'])
@pytest.mark.parametrize('container,dtype,first_label',[('csr','float32',-3),('csc','float32',7)])
def test_represented_sparse_inputs_and_offset_labels_match_native_answers(row,container,dtype,first_label):
    # The original inputs are binary halves/eighths, exactly represented in
    # both dtypes; do not use float64 answers for rounded float32 inputs.
    assert np.array_equal(np.asarray(row['case']['x'],dtype=dtype).astype(float),row['case']['x'])
    actual=contract.observe(row['case'],container=container,dtype=dtype,first_label=first_label)
    assert contract.equal(actual,contract.expected_for_label(row,first_label))


def test_native_answers_and_every_historical_request_are_authenticated():
    fixture=contract.check_identity()
    assert len(fixture['rows'])==64
    assert len(contract.historical_cases())==72
    assert fixture['coverage_note'].startswith('Finite64-input')


def test_registered_native_fitting_controls_leave_whole_method_coverage_open():
    from reproducibility.validation_registry import FAMILIES
    from reproducibility.run import inventory
    assert FAMILIES['ordinal-native-fitting']=='reproducibility.ordinal_fitting_contract'
    keys={'ordinal-native-fit.'+row['case']['key'] for row in contract.cases()}
    keys.update('ordinal-native-fit.'+row['request_key'] for row in contract.historical_cases())
    assert len(keys)==136
    rows=inventory(keys)
    for capability in contract.CAPABILITIES:
        owner=next(row for row in rows if row['capability']==capability)
        assert owner['status']=='partially-validated-contract'
        assert set(owner['executed_subcontracts'].split(';'))==keys


def test_failed_fit_preserves_the_full_request_and_later_comparisons(tmp_path,monkeypatch):
    answers={row['case']['key']:row for row in contract.cases()}
    failed=contract.cases()[2]['case']['key']
    calls=[]
    def observation(case,**options):
        calls.append(case['key'])
        if case['key']==failed:
            raise ArithmeticError('Injected failed native refinement')
        return contract.expected_for_label(answers[case['key']],options.get('first_label',0))
    monkeypatch.setattr(contract,'observe',observation)
    rows=contract.validate(tmp_path)
    assert len(rows)==len(calls)==136
    assert sum(row['status']=='disagree' for row in rows)==1
    paired=json.loads((tmp_path/'ordinal-native-fit-paired.json').read_text(encoding='utf-8'))['rows']
    assert len(paired)==136 and paired[2]['case']==answers[failed]['case']
    assert paired[2]['unchanged_native']==answers[failed]['expected']
    assert 'ArithmeticError: Injected failed native refinement' in paired[2]['error']
    assert rows[-1]['status']=='agree' and paired[-1]['error'] is None


@pytest.mark.parametrize('row',contract.cases()[60:],ids=lambda row:row['case']['key'])
@pytest.mark.parametrize('container',['array','dataframe','csr','csc'])
@pytest.mark.parametrize('max_iter',[25,10000])
def test_offered_alpha100_setting_matches_both_native_families_with_offset_labels(row,container,max_iter):
    assert row['case']['alpha']==100
    assert len(row['qualification']['independent_families'])==2
    actual=contract.observe(row['case'],container=container,first_label=7,max_iter=max_iter)
    assert contract.equal(actual,contract.expected_for_label(row,7))


@pytest.mark.parametrize('field',['coefficients','thresholds','probabilities','predictions'])
def test_altered_native_answer_fails_identity(tmp_path,monkeypatch,field):
    fixture=json.loads(contract.FIXTURE.read_text(encoding='utf-8'))
    value=fixture['rows'][0]['expected'][field]
    if field=='probabilities':value[0][0]+=0.1
    else:value[0]+=1
    path=tmp_path/'changed.json';path.write_text(json.dumps(fixture),encoding='utf-8')
    monkeypatch.setattr(contract,'FIXTURE',path)
    with pytest.raises(ValueError,match='differ from unchanged native'):
        contract.check_identity()


@pytest.mark.parametrize('container',['array','csr'])
def test_exact_feature_null_direction_prevents_false_positive_curvature(container):
    from PyFLASH.modelling import _PyFLASHOrdinalLogistic
    case=next(row['case'] for row in contract.cases() if row['case']['key']=='retained-numeric-0')
    raw=np.asarray(case['x']);x=np.column_stack((raw[:,0],2*raw[:,0]))
    assert all(2*Fraction.from_float(float(a))-Fraction.from_float(float(b))==0 for a,b in x)
    operand=sparse.csr_matrix(x) if container=='csr' else x
    model=_PyFLASHOrdinalLogistic(alpha=0,max_iter=10000).fit(operand,np.asarray(case['y']))
    assert not model._ordinal_fit_diagnostics['identifiable_free_curvature']
    assert not model._ordinal_fit_diagnostics['refined']
    assert model._ordinal_fit_diagnostics['refinement_iterations']==0


def test_unsuccessful_native_refinement_keeps_the_preceding_answer(monkeypatch):
    from types import SimpleNamespace
    import mord.threshold_based as threshold
    from PyFLASH.modelling import _PyFLASHOrdinalLogistic
    case=next(row['case'] for row in contract.cases() if row['case']['key']=='retained-numeric-0')
    x=np.asarray(case['x']);y=np.asarray(case['y'])
    before=threshold.threshold_fit(x,y,case['alpha'],case['classes'],mode='0-1',max_iter=10000,tol=1e-16)
    monkeypatch.setattr(optimize,'root',lambda fun,initial,**kwargs:SimpleNamespace(success=False,nit=1,message='Injected unsuccessful native fit',x=initial+100))
    model=_PyFLASHOrdinalLogistic(alpha=case['alpha'],max_iter=10000).fit(x,y)
    assert np.array_equal(model.model_.coef_,before[0])
    assert np.array_equal(model.model_.theta_,before[1])
    assert not model._ordinal_fit_diagnostics['refined']


def test_exact_rank_guard_does_not_confuse_one_bit_distinction_with_duplicate_features():
    from PyFLASH.modelling import _PyFLASHOrdinalLogistic
    x=np.array([[1.,1.],[2.,2.],[3.,3.],[4.,4.]])
    model=_PyFLASHOrdinalLogistic(alpha=0)
    assert not model._has_full_affine_feature_rank(x)
    x[0,1]=np.nextafter(x[0,1],np.inf)
    assert model._has_full_affine_feature_rank(x)


def test_refitting_an_exact_zero_model_clears_previous_refinement_status():
    from PyFLASH.modelling import _PyFLASHOrdinalLogistic
    rows=contract.cases()
    ordinary=next(row['case'] for row in rows if row['case']['key']=='retained-numeric-0')
    zero=next(row['case'] for row in rows if all(value==0 for field in ('coefficients','thresholds') for value in row['expected'][field]))
    model=_PyFLASHOrdinalLogistic(alpha=ordinary['alpha']).fit(np.asarray(ordinary['x']),np.asarray(ordinary['y']))
    assert model._ordinal_fit_diagnostics['refined']
    model.set_params(alpha=zero['alpha'])
    model.fit(np.asarray(zero['x']),np.asarray(zero['y']))
    assert not hasattr(model,'_ordinal_fit_diagnostics')
    assert np.array_equal(model.model_.coef_,np.zeros(len(zero['x'][0])))
