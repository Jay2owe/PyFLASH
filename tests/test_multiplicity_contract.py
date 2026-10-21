"""Every method/alias, complete arrays, missingness and independent frozen answers."""
import hashlib
import json
import numpy as np
import pytest
from reproducibility import multiplicity_contract as contract

REFERENCE = json.loads(contract.FIXTURE.read_text(encoding='utf-8'))


@pytest.mark.parametrize('row',REFERENCE['rows'],ids=lambda row:row['key'])
@pytest.mark.parametrize('reference',['values','exact_benchmark'])
def test_complete_adjustment_contract(row,reference):
    expected = [np.nan if v is None else v for v in row[reference]]
    np.testing.assert_allclose(contract.production(row),expected,rtol=1e-9,atol=1e-12,equal_nan=True)


def test_native_reference_source_and_every_case_remain_frozen():
    assert hashlib.sha256(open(contract.__file__,'rb').read()).hexdigest() == REFERENCE['reference_code_sha256']
    assert [{key:row[key] for key in ('key','capability','parameters','canonical')}
            for row in REFERENCE['rows']] == contract.cases()
    from statsmodels.stats.multitest import multitest_alias
    assert set(multitest_alias) == {alias for aliases in contract.ALIASES.values() for alias in aliases}


@pytest.mark.parametrize('values',[[-.1],[1.1],[.1,-1],[]])
def test_invalid_method_is_rejected_even_without_finite_values(values):
    from PyFLASH.stats_extra import adjust_pvalues
    with pytest.raises(ValueError):
        adjust_pvalues(values,method='unknown-method')


@pytest.mark.parametrize('values',[[-.1],[1.1],[.1,-1]])
def test_invalid_finite_probabilities_are_rejected(values):
    from PyFLASH.stats_extra import adjust_pvalues
    with pytest.raises(ValueError,match='probabilit'):
        adjust_pvalues(values)
