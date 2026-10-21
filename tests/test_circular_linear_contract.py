"""All circular association outputs frozen before the numerical correction."""
import hashlib
import json
from pathlib import Path
import numpy as np
import pytest
from reproducibility import circular_linear_contract as contract
from reproducibility.reference_runtime import values

REFERENCE = json.loads(contract.FIXTURE.read_text(encoding='utf-8'))


@pytest.mark.parametrize('row', REFERENCE['rows'], ids=lambda row: row['key'])
@pytest.mark.parametrize('reference', ['native-R','statsmodels','mathematical'])
def test_complete_circular_linear_outputs(row, reference):
    np.testing.assert_allclose(contract.production(row), values(row['references'][reference]),
                               rtol=1e-9, atol=1e-12, equal_nan=True)


def test_input_and_reference_adapter_identity_remain_frozen():
    assert hashlib.sha256(Path(contract.__file__).read_bytes()).hexdigest() == REFERENCE['reference_code_sha256']
    assert [{k: row[k] for k in ('key','capability','parameters')} for row in REFERENCE['rows']] == contract.cases()


@pytest.mark.parametrize('period', [0,-1,np.nan,np.inf,True,'24',None])
@pytest.mark.parametrize('data', [[],[1,2,3,4]])
def test_invalid_period_rejected_before_empty_or_other_degenerate_return(period,data):
    from PyFLASH.stats_extra import circular_linear_corr
    with pytest.raises(ValueError, match='period'):
        circular_linear_corr(data,data,period=period)


def test_pairing_rejects_mismatched_lengths_and_preserves_missing_input_series():
    import pandas as pd
    from PyFLASH.stats_extra import circular_linear_corr
    with pytest.raises(ValueError, match='same number'):
        circular_linear_corr([1,2,3,4],[1,2])
    theta = pd.Series([1,2,pd.NA,6,8,13,16,21],dtype=object)
    x = pd.Series([2,1,3,5,None,7,8,6],dtype=object)
    before_t,before_x = theta.copy(deep=True),x.copy(deep=True)
    assert circular_linear_corr(theta,x)['n'] == 6
    pd.testing.assert_series_equal(theta,before_t)
    pd.testing.assert_series_equal(x,before_x)
