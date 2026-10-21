"""Ledger originals come from source cells, including repeated flag requests."""
import json
import pytest
from reproducibility import outlier_ledger_source_contract as contract


@pytest.mark.parametrize('case',contract.cases(),ids=lambda row:row['key'])
def test_ledger_records_selected_source_values(case,tmp_path):
    actual=contract.production(case,tmp_path)
    if actual!=case['expected']:
        (tmp_path/'unresolved-observation.json').write_text(
            json.dumps(dict(case=case,actual=actual),indent=2,allow_nan=False),encoding='utf-8')
    assert actual==case['expected']


def test_frozen_source_value_expectations_reproduce_without_candidate_calls():
    import runpy
    expected=runpy.run_path(str(contract.ARCHIVE/'reference-producer.py'))['expected']
    for case in contract.cases():assert expected(case)==case['expected']


def test_reapplying_reviewed_ledger_keeps_its_historical_original(tmp_path):
    from types import SimpleNamespace
    import pandas as pd
    from PyFLASH.exclusions import apply_exclusions
    source=pd.DataFrame(dict(AnimalName=['S5'],X=['EXCLUDED_MANUAL:review']))
    ledger=pd.DataFrame([dict(AnimalName='S5',column='X',group='',original_value=100.,
        kind='manual',reason='review',scope='cell',fill='EXCLUDED_MANUAL:review')])
    ledger.attrs['_pyflash_exclusion_rois']=['SCN']
    exp=SimpleNamespace(summary=source,summaries={'SCN':source},exclusions=ledger,
        exclusion_summary={'roi':'SCN'},data_path=str(tmp_path))
    result=apply_exclusions(exp)
    assert result.exclusions['original_value'].eq(100.).all()
    assert source.loc[0,'X']=='EXCLUDED_MANUAL:review'
