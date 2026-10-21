"""Every field of the independently frozen scalar estimator cases agrees."""
import json
import numpy as np
import pytest
from reproducibility.scalar_contracts import FIXTURE, production, reference
from reproducibility.cases import RTOL, ATOL


@pytest.mark.parametrize('row', json.loads(FIXTURE.read_text(encoding='utf-8'))['rows'], ids=lambda row: row['key'])
def test_independent_scalar_contract(row):
    expected = [np.nan if value is None else value for value in row['expected']]
    np.testing.assert_allclose(reference(row), expected, rtol=RTOL, atol=ATOL, equal_nan=True)
    np.testing.assert_allclose(production(row), expected, rtol=RTOL, atol=ATOL, equal_nan=True)


@pytest.mark.slow
def test_complete_scalar_gate_requires_every_case_and_never_promotes_parent():
    from reproducibility.run import inventory
    from reproducibility.scalar_contracts import cases
    from reproducibility.finite_scale_contract import cases as unit_cases
    from reproducibility.scalar_input_contract import cases as input_cases
    executed = ['scalar.'+row['key'] for row in cases()]
    rows = {row['capability']: row for row in inventory(executed)}
    # Ordinary scalar answers alone cannot close the newly extended unit gate.
    assert sum(row['status'] == 'validated-complete-contract' for row in rows.values()) == 3
    for name in ('cohens_d','hedges_g'):
        assert rows['PyFLASH.stats_extra.'+name]['status'] != 'validated-complete-contract'
    executed += [row['key'] for row in unit_cases() if row['method'] in {'cohens_d','hedges_g'}]
    rows = {row['capability']: row for row in inventory(executed)}
    assert sum(row['status'] == 'validated-complete-contract' for row in rows.values()) == 3
    executed += [row['key'] for row in input_cases()]
    rows = {row['capability']: row for row in inventory(executed)}
    assert sum(row['status'] == 'validated-complete-contract' for row in rows.values()) == 5
    from reproducibility.scalar_multiplicity_contract import cases as correction_cases
    for name in ('bonferroni_correction','sidak_correction'):
        assert rows['PyFLASH.stats.'+name]['status'] != 'validated-complete-contract'
    executed += [row['key'] for row in correction_cases()]
    rows = {row['capability']: row for row in inventory(executed)}
    assert sum(row['status'] == 'validated-complete-contract' for row in rows.values()) == 7
    assert rows['PyFLASH.stats_extra.effect_sizes_for_test']['status'] != 'validated-complete-contract'
    assert rows['mean_bars']['status'] != 'validated-complete-contract'
    executed.remove('scalar.cohens_d.0.False')
    rows = {row['capability']: row for row in inventory(executed)}
    assert rows['PyFLASH.stats_extra.cohens_d']['status'] != 'validated-complete-contract'
    executed.append('scalar.cohens_d.0.False')
    executed.remove('finite-scale.cohens_d.balanced.-600')
    rows = {row['capability']: row for row in inventory(executed)}
    assert rows['PyFLASH.stats_extra.cohens_d']['status'] != 'validated-complete-contract'
