"""Independently frozen public options, owner protocols and saved native ledgers."""
import json
import pytest
from reproducibility import outlier_options_contract as contract


@pytest.mark.parametrize('case',contract.cases(),ids=lambda row:row['key'])
def test_exposed_outlier_options(case,tmp_path):
    actual=contract.production(case,tmp_path)
    if actual!=case['expected']:
        (tmp_path/'unresolved-observation.json').write_text(
            json.dumps(dict(case=case,actual=actual),indent=2,allow_nan=False),encoding='utf-8')
    assert actual==case['expected']


@pytest.mark.parametrize('api',['mark_outliers','exclude_outliers'])
def test_detection_skips_auxiliary_overview_work(api,tmp_path,monkeypatch):
    from PyFLASH import pipeline
    def forbidden(*args,**kwargs):
        raise AssertionError('Outlier-only detection requested unrelated overview calculations')
    for name in ('_ovw_condition_distribution_stats','_ovw_effect_sizes','_ovw_significance_audit',
                 '_ovw_scorecard','_ovw_readiness','_ovw_power_mde'):
        monkeypatch.setattr(pipeline,name,forbidden)
    case=next(row for row in contract.cases() if row['api']==api and row['variant']=='baseline' and row['scope']=='cell')
    actual=contract.production(case,tmp_path)
    if actual!=case['expected']:
        (tmp_path/'unresolved-observation.json').write_text(
            json.dumps(dict(case=case,actual=actual),indent=2,allow_nan=False),encoding='utf-8')
    assert actual==case['expected']
