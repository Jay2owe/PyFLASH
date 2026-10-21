"""Complete circular group inference and retained reference limitations."""
import hashlib
import json
from pathlib import Path
import numpy as np
import pytest
from reproducibility import watson_williams_contract as contract
from reproducibility.reference_runtime import values

REFERENCE = json.loads(contract.FIXTURE.read_text(encoding='utf-8'))


@pytest.mark.parametrize('row',REFERENCE['rows'],ids=lambda row:row['key'])
@pytest.mark.parametrize('reference',['native-R','mathematical'])
def test_complete_group_inference(row,reference):
    np.testing.assert_allclose(contract.production(row),values(row['references'][reference]),
                               rtol=1e-9,atol=1e-12,equal_nan=True)


@pytest.mark.parametrize('row',[row for row in REFERENCE['rows'] if row['pycircstat2_agrees']],ids=lambda row:row['key'])
def test_frozen_accepted_package_all_fields(row):
    np.testing.assert_allclose(contract.production(row),values(row['pycircstat2']),
                               rtol=1e-9,atol=1e-12,equal_nan=True)


def test_frozen_definition_inputs_and_reference_artifacts_remain_visible():
    assert hashlib.sha256(Path(contract.__file__).read_bytes()).hexdigest()==REFERENCE['reference_code_sha256']
    assert [{k:row[k] for k in ['key','capability','parameters']} for row in REFERENCE['rows']]==contract.cases()
    affected = [row['key'] for row in REFERENCE['rows'] if not row['pycircstat2_agrees']]
    assert set(affected)=={f'watson.williams.{name}.{period}'
        for name in ['uniform','constant_same'] for period in [1.,24.,360.]}
    assert all(row['pycircstat2_scope']=='verified-degenerate-roundoff-artifact'
               for row in REFERENCE['rows'] if row['key'] in affected)


def test_period_validation_and_missing_values_do_not_mutate_groups():
    from PyFLASH.stats_extra import watson_williams
    import pandas as pd
    group = pd.Series([1,2,None,pd.NA,4],dtype=object)
    before = group.copy(deep=True)
    answer = watson_williams([group,[2,3,4,5]])
    assert answer['n']==7
    pd.testing.assert_series_equal(group,before)
    for period in [0,-1,np.inf,np.nan,True,None,'24']:
        with pytest.raises(ValueError,match='period'):
            watson_williams([],period=period)
