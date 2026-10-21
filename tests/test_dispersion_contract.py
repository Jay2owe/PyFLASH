"""Full spread inference with native ranks and separately calculated geometry."""
import hashlib
import json
from pathlib import Path
import numpy as np
import pytest
from reproducibility import dispersion_contract as contract, dispersion_decimal
from reproducibility.reference_runtime import values

REFERENCE = json.loads(contract.FIXTURE.read_text(encoding='utf-8'))


@pytest.mark.parametrize('row',REFERENCE['rows'],ids=lambda row:row['key'])
@pytest.mark.parametrize('reference',['decimal-native-R','mathematical'])
def test_all_returned_spread_fields(row,reference):
    np.testing.assert_allclose(contract.production(row),values(row['references'][reference]),
                               rtol=1e-9,atol=1e-12,equal_nan=True)


def test_independent_fixture_sources_and_input_identity():
    assert hashlib.sha256(Path(contract.__file__).read_bytes()).hexdigest()==REFERENCE['reference_code_sha256']
    assert hashlib.sha256(Path(dispersion_decimal.__file__).read_bytes()).hexdigest()==REFERENCE['decimal_code_sha256']
    assert [{k:row[k] for k in ['key','capability','parameters']} for row in REFERENCE['rows']]==contract.cases()
    assert all(row['published_R_scope']=='precision-sensitive-rank-diagnostic'
               for row in REFERENCE['rows'] if not row['published_R_agrees'])


def test_invalid_period_and_missing_input_preservation():
    import pandas as pd
    from PyFLASH.stats_extra import circular_dispersion_test
    data = pd.Series([1,2,None,pd.NA,4,np.inf],dtype=object)
    before = data.copy(deep=True)
    assert circular_dispersion_test([data,[3,4,7]])['n']==6
    pd.testing.assert_series_equal(data,before)
    for period in [0,-1,np.inf,np.nan,True,None,'24']:
        with pytest.raises(ValueError,match='period'):
            circular_dispersion_test([],period=period)
