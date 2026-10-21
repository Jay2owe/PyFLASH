"""Whole subject identities, column layout and areas, from two independent engines."""
import json
import numpy as np
import pytest
from reproducibility import auc_contract as contract
from reproducibility.cases import RTOL, ATOL
from reproducibility.reference_runtime import values

REFERENCE = json.loads(contract.FIXTURE.read_text(encoding='utf-8'))


@pytest.mark.parametrize('row',REFERENCE['rows'],ids=lambda row:row['key'])
@pytest.mark.parametrize('reference',['native-R','exact-rational'])
def test_entire_timecourse_table(row,reference):
    expected = values(row) if reference == 'native-R' else row['mathematical_values']
    np.testing.assert_allclose(contract.production(row),expected,rtol=RTOL,atol=ATOL,equal_nan=True)


def test_native_query_inputs_and_exact_benchmarks_preserved():
    assert [{k:row[k] for k in ('key','capability','parameters')} for row in REFERENCE['rows']] == contract.cases()
    assert REFERENCE['wasm_sha256'] and REFERENCE['webR']=='0.6.0'
    for row in REFERENCE['rows']:
        assert row['code']==contract.r_query(row)
        np.testing.assert_allclose(contract.mathematical(row),values(row),rtol=RTOL,atol=ATOL)


@pytest.mark.parametrize('baseline',[float('nan'),float('inf'),-float('inf')])
def test_nonfinite_baseline_rejected(baseline):
    import pandas as pd
    from PyFLASH.stats_extra import timecourse_auc
    with pytest.raises(ValueError,match='baseline'):
        timecourse_auc(pd.DataFrame({'AnimalName':['a','a'],'Time':[0,1],'Signal':[1,2]}),
                       'Time','Signal',baseline=baseline)
