"""Small tails remain positive and one bounded owner serves all consumers."""
import math
import pytest
from PyFLASH._studentized_range import range_tail
from reproducibility import one_way_validation as validation

@pytest.mark.parametrize('case',validation.range_cases(),ids=lambda r:r['key'])
def test_range_tail_matches_independent_direct_event(case):
    p=case['parameters'];actual=range_tail(p['threshold'],p['count'],float(p['degrees']))
    assert math.isclose(actual,case['expected'],rel_tol=1e-9,abs_tol=0.)

@pytest.mark.parametrize('case',validation.helper_cases(),ids=lambda r:r['key'])
def test_scalar_sidak_tail_retains_small_positive_probabilities(case):
    from PyFLASH import stats
    from reproducibility.one_way_contract import clean,equal
    actual=validation.helper_production(case)
    assert equal(actual,validation.helper_response(case),('pvalues',))

@pytest.mark.parametrize('change',['input','response','classification','reason'])
def test_versioned_request_boundary_refuses_changed_evidence(tmp_path,monkeypatch,change):
    import json
    fixture=json.loads(validation.SIDAK_REQUEST_BOUNDARY.read_text())
    if change=='input':fixture['rows'][0]['original_case']['parameters']['p_value']=.7
    elif change=='response':fixture['rows'][-1]['public_response']=0.
    elif change=='classification':fixture['rows'][-1]['classification']='numeric-tail-comparison'
    else:fixture['reason']='unreviewed replacement'
    path=tmp_path/'changed-boundary.json';path.write_text(json.dumps(fixture))
    monkeypatch.setattr(validation,'SIDAK_REQUEST_BOUNDARY',path)
    with pytest.raises(ValueError,match='request boundary changed'):
        validation.helper_response(validation.helper_cases()[0])

def test_only_bounded_scalar_results_are_cached():
    range_tail.cache_clear()
    for index in range(300):range_tail(index/40.,2,80.)
    assert range_tail.cache_info().maxsize==256
    assert range_tail.cache_info().currsize==256
    previous=range_tail.cache_info().hits
    range_tail(299/40.,2,80.)
    assert range_tail.cache_info().hits==previous+1
