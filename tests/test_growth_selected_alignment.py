from pathlib import Path
import hashlib
import json
import numpy as np
import pytest
from PyFLASH.stats_extra import fit_growth_curve

FIXTURE=Path(__file__).resolve().parents[1]/'reproducibility/fixtures/growth_selected_reference.json'
REFERENCE=json.loads(FIXTURE.read_text())
NAMES={'exponential':['amplitude','rate','offset'],'logistic':['bottom','top','ec50','hill']}

@pytest.mark.parametrize('case',REFERENCE['rows'],ids=lambda row:row['key'])
def test_selected_growth_fit_matches_complete_independent_outputs(case):
    p=case['parameters']
    x=np.array([np.nan if v is None else float(v) for v in p['x']])
    y=np.array([np.nan if v is None else float(v) for v in p['y']])
    original_x,original_y=x.copy(),y.copy()
    answer=fit_growth_curve(x,y,model=p['model'])
    assert set(answer)=={'model','params','r_squared','aic','n','predict','all_models'}
    assert answer['model']==p['model']
    assert list(answer['params'])==NAMES[p['model']]
    assert list(answer['all_models'])==[p['model']]
    names=NAMES[p['model']]
    actual=[2 if p['model']=='exponential' else 3,answer['n'],
        *[answer['params'][name]['value'] for name in names],
        *[answer['params'][name]['stderr'] for name in names],answer['r_squared'],answer['aic'],
        *answer['predict'](p['prediction_x']).tolist(),answer['all_models'][p['model']]['aic']]
    for expected in [case['expected'],case['native_R_expected']]:
        np.testing.assert_allclose(actual,expected,**REFERENCE['tolerance'],equal_nan=True)
    np.testing.assert_array_equal(x,original_x)
    np.testing.assert_array_equal(y,original_y)

def test_selected_reference_inputs_and_code_have_frozen_identity():
    from reproducibility.growth_selected_contract import cases, normalised_identity
    source=Path(__file__).resolve().parents[1]/'reproducibility/growth_stationary_reference.py'
    assert hashlib.sha256(source.read_bytes()).hexdigest()==REFERENCE['reference_code_sha256']
    assert [{k: row[k] for k in ('key', 'capability', 'parameters')}
            for row in REFERENCE['rows']] == cases()
    for row in REFERENCE['rows']:
        p=row['parameters']
        finite=sorted((float(x),float(y)) for x,y in zip(p['x'],p['y'])
            if x is not None and y is not None and np.isfinite(float(x)) and np.isfinite(float(y)))
        canonical={**p,'x':[v[0] for v in finite],'y':[v[1] for v in finite]}
        assert hashlib.sha256(json.dumps(canonical,sort_keys=True,separators=(',',':')).encode()).hexdigest()==row['normalised_input_sha256']
        assert normalised_identity(row) == row['normalised_input_sha256']
