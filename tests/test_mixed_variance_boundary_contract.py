"""Small positive random variance must not silently select the zero boundary."""
import json
import hashlib
import numpy as np
import pandas as pd
import pytest
from PyFLASH.stats_extra import cosinor_table
from reproducibility import mixed_variance_boundary_contract as reference
from reproducibility.reference_runtime import values
from reproducibility import mixed_rhythm_contract as likelihood
from reproducibility.cosinor_table_contract import FIELDS

@pytest.mark.parametrize('case',reference.cases(),ids=lambda r:r['key'])
def test_complete_small_variance_fit_matches_independent_answers(case):
    fixture=json.loads(reference.FIXTURE.read_text(encoding='utf-8'))
    row=next(r for r in fixture['rows'] if r['case']['key']==case['key'])
    assert case==row['case'] and 0<row['diagnostics']['lambda']<1e-6
    expected=values(row['mathematical']);actual=reference.production(case)
    np.testing.assert_allclose(actual,expected,rtol=1e-9,atol=1e-12,equal_nan=True)
    np.testing.assert_allclose(actual[5],expected[5],rtol=1e-9,atol=0.)
    data=pd.DataFrame(case['parameters']['records'],columns=['t','y','animal'])
    table=cosinor_table(data,'t','y',animal_col='animal',method='mixed',period=case['parameters']['period'])
    assert list(table.columns)==FIELDS and len(table)==1
    row=table.iloc[0];assert row['method']=='mixed' and row['group']=='all' and row['n']==len(data) and row['error'] is None
    np.testing.assert_allclose([row[k] for k in likelihood.FIELDS],expected,rtol=1e-9,atol=1e-12,equal_nan=True)
    np.testing.assert_allclose(row['p_rhythm'],expected[5],rtol=1e-9,atol=0.)

def test_small_variance_reference_identity_and_original_failure_record():
    fixture,queries=reference.check_identity();assert len(queries)==18 and len(fixture['original_failures'])==18
    previous=reference.FIXTURE.with_name('mixed_variance_boundary_reference.json')
    assert hashlib.sha256(previous.read_bytes()).hexdigest()==fixture['previous_fixture_sha256']
    original=json.loads(previous.read_text(encoding='utf-8'))
    assert original['rows']==fixture['rows'] and original['native']==fixture['native']
    for row,native in zip(fixture['rows'],fixture['native']['rows'],strict=True):
        assert not row['original_agrees']
        expected=values(row['mathematical']);fresh=reference.mathematical(row['case'])
        np.testing.assert_allclose(fresh,expected,rtol=1e-9,atol=1e-12,equal_nan=True)
        np.testing.assert_allclose(values(native),expected,rtol=1e-9,atol=1e-12,equal_nan=True)
        np.testing.assert_allclose(values(native)[5],expected[5],rtol=1e-9,atol=0.)
