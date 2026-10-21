"""Independently addressed matrix cells lock public extraction and its bounds."""
import json
import numpy as np
import pytest
from reproducibility import comparison_index_contract as reference


@pytest.mark.parametrize('row', json.loads(reference.FIXTURE.read_text())['rows'], ids=lambda row:row['key'])
def test_complete_literal_matrix_contract(row):
    np.testing.assert_array_equal(reference.reference(row),row['expected'])
    np.testing.assert_array_equal(reference.production(row),row['expected'])


def test_extraction_gate_requires_every_case_and_preserves_statistical_parent_gap():
    from reproducibility.run import inventory
    executed = [row['key'] for row in reference.cases()]
    rows = {row['capability']:row for row in inventory(executed)}
    assert rows[reference.CAPABILITY]['status'] == 'validated-complete-contract'
    assert rows['PyFLASH.stats.multipleComparisons']['status'] != 'validated-complete-contract'
    partial = {row['capability']:row for row in inventory(executed[1:])}
    assert partial[reference.CAPABILITY]['status'] != 'validated-complete-contract'
