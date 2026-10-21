"""Malformed public samples cannot be flattened into a reported effect."""
from copy import deepcopy
import pytest
from reproducibility import scalar_input_contract as contract

@pytest.mark.parametrize('case',contract.cases(),ids=lambda row:row['key'])
def test_public_effect_shape_preflight(case):
    original=deepcopy(case)
    assert contract.production(case)==case['expected']
    assert case==original

def test_original_shape_evidence_is_retained():
    fixture=contract.check_identity()
    assert len(fixture['rows'])==42
    assert sum(row['original_failure'] for row in fixture['rows'])==36
