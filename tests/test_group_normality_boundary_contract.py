"""Eligibility does not depend on normality; every plotting call binds its API."""
import pytest
from reproducibility import group_normality_boundary_contract as contract

@pytest.mark.parametrize('case',contract.cases(),ids=lambda row:row['key'])
def test_pipeline_boundary_matches_before_correction_requirement(case,tmp_path):
    answer=contract.observe(case,tmp_path/case['key'])
    assert answer['agrees']
    if case['reference']['skip_constant_marker']:
        assert answer['complete_original_output']['results']==[]
        assert len(answer['complete_original_output']['descriptives'])==2
    else:
        assert len(answer['complete_original_output']['results'])==1
        assert answer['complete_original_output']['bar_calls']

def test_all_original_failures_retained_and_pipeline_not_certified_complete():
    fixture=contract.check_identity();assert len(fixture['rows'])==12
    assert all(not row['agrees'] for row in fixture['rows'])
    from reproducibility.run import inventory
    row=next(row for row in inventory({case['key'] for case in contract.cases()}) if row['capability']=='PyFLASH.pipeline.group_comparison')
    assert row['status']=='partially-validated-contract'
