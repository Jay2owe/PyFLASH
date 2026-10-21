"""Complete supplied-state responses and preserved evidence/scope boundaries."""
from copy import deepcopy
import json
import pytest
from reproducibility import ordinal_response_contract as contract

@pytest.mark.parametrize('row',contract.cases(),ids=lambda row:row['case']['key'])
def test_all_supplied_state_responses(row):
    untouched=deepcopy(row);answer=contract.reference.report(row['case'])
    assert contract.equal(answer,row['expected'])
    assert contract.equal(contract.production(row['case']),answer)
    assert row==untouched

def test_original_failures_and_native_diagnostics_are_retained():
    fixture=contract.check_identity();rows=fixture['rows']
    assert len(rows)==72
    assert sum(row['original_failure'] for row in rows[:54])==36
    assert sum(not row['native_agrees'] for row in rows[:54])==12
    assert sum(row['original_failure'] for row in rows[54:])>=12

def test_supplied_states_do_not_certify_general_fit_or_response_options():
    from reproducibility.run import inventory
    keys={row['case']['key'] for row in contract.cases()}
    owners={row['capability']:row for row in inventory(keys)}
    for name in contract.CAPABILITIES:
        assert owners[name]['status']=='partially-validated-contract'
    assert owners['PyFLASH.modelling._PyFLASHOrdinalLogistic.fit']['status']!='validated-contract'

def test_altered_probability_is_rejected(tmp_path,monkeypatch):
    fixture=json.loads(contract.FIXTURE.read_text(encoding='utf-8'))
    fixture['rows'][0]['expected']['probabilities'][0][0]=.999
    path=tmp_path/'changed.json';path.write_text(json.dumps(fixture),encoding='utf-8')
    monkeypatch.setattr(contract,'FIXTURE',path)
    with pytest.raises(ValueError,match='differ from original'):contract.check_identity()

@pytest.mark.parametrize('row',[row for row in contract.cases()
    if row['case']['container']=='array' and row['case']['profile'] in
       {'binary-centre','binary-small-tail','dot-cancellation','product-underflow'}],
    ids=lambda row:row['case']['key'])
def test_one_dimensional_rows_preserve_single_row_prediction_shape(row):
    import numpy as np
    from mord import LogisticIT
    from PyFLASH.modelling import _PyFLASHOrdinalLogistic
    case=row['case'];model=_PyFLASHOrdinalLogistic()
    model.classes_=np.arange(len(case['theta'])+1)+case['first_label']
    model.model_=LogisticIT();model.model_.coef_=np.array(case['coef'])
    model.model_.theta_=np.array(case['theta']);model.model_.classes_=model.classes_.copy()
    value=model.predict(np.array(case['x'][0]))
    assert isinstance(value,np.ndarray) and value.shape==(1,)
    assert value.tolist()==row['expected']['predictions'][:1]
    assert contract.equal(model.predict_proba(np.array(case['x'][0])).tolist(),
                          row['expected']['probabilities'][:1])
