"""Native published and literal conventions freeze the full scalar output."""
import json
import numpy as np
import pytest
from reproducibility import effect_magnitude_contract as reference

FROZEN = json.loads(reference.FIXTURE.read_text())['rows']


@pytest.mark.parametrize('row',FROZEN,ids=lambda row:row['key'])
def test_magnitude_against_frozen_published_rules(row):
    np.testing.assert_array_equal(reference.reference(row),row['expected'])
    np.testing.assert_array_equal(reference.production(row),row['expected'])
    if row['parameters']['kind']=='d':
        from PyFLASH.stats_extra import interpret_magnitude
        assert interpret_magnitude(row['parameters']['value']) == row['expected_label']


def test_rank_biserial_report_uses_correlation_conventions():
    from PyFLASH.stats_extra import effect_sizes_for_test
    result = effect_sizes_for_test([[1,2,3,4,5],[2,3,4,5,6]], 'Mann-Whitney', ['1-2'],ci=False)
    pair = result['pairwise'][0]
    assert pair['metric'] == 'rank_biserial_r'
    assert pair['value'] == pytest.approx(-.36)
    assert pair['interpretation'] == 'medium'


@pytest.mark.slow
def test_only_complete_classifier_cases_close_the_scalar_gate():
    from reproducibility.run import inventory
    executed = [row['key'] for row in reference.cases()]
    rows = {row['capability']:row for row in inventory(executed)}
    assert rows[reference.CAPABILITY]['status'] == 'validated-complete-contract'
    assert rows['PyFLASH.stats_extra.effect_sizes_for_test']['status'] != 'validated-complete-contract'
    rows = {row['capability']:row for row in inventory(executed[1:])}
    assert rows[reference.CAPABILITY]['status'] != 'validated-complete-contract'
