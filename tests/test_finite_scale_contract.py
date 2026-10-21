"""Accepted dimensionless outputs must survive finite measurement-unit changes."""
import pytest
from reproducibility import finite_scale_contract as reference

@pytest.mark.parametrize('case', reference.cases(), ids=lambda row: row['key'])
def test_finite_unit_changes_against_preserved_independent_answers(case):
    assert reference.equal(reference.production(case), case['expected'])

def test_binary_scaling_reference_inputs_and_provenance_are_preserved():
    assert len(reference.check_identity()['rows']) == 16
