"""Published normality calibration, undefined inputs and stable tail probabilities."""
import pytest
from PyFLASH.stats import modified_anderson
from reproducibility import anderson_contract as reference

@pytest.mark.parametrize('case',reference.cases(),ids=lambda row:row['key'])
def test_fitted_normality_against_independently_frozen_answers(case):
    assert reference.equal(reference.production(case),reference.expected(case))

def test_normality_reference_identity_and_retained_failures():
    fixture=reference.check_identity()
    assert len(fixture['rows'])==75 and len(fixture['original_failures'])==72
    assert sum('native' in r for r in fixture['rows'])==70
    assert sum('native' in r and r['reference_artifact'] is None for r in fixture['rows'])==54

@pytest.mark.parametrize('values',[1,[[1,2],[3,4]]])
def test_normality_requires_a_one_dimensional_sample(values):
    with pytest.raises(ValueError):modified_anderson(values)

def test_changed_positive_tail_probability_cannot_be_accepted_as_zero():
    case=next(c for c in reference.cases() if reference.expected(c)[1] is not None and reference.expected(c)[1]<1e-20)
    original=reference.expected(case);changed=[original[0],0.0]
    assert not reference.equal(changed,original)
