"""Captions cannot select other groups and failed exports preserve old files."""
from copy import deepcopy
from pathlib import Path
import pytest
from reproducibility import print_export_contract as contract

@pytest.mark.parametrize('case',contract.cases(),ids=lambda row:row['key'])
def test_complete_functional_report_contract(case,tmp_path):
    original=deepcopy(case)
    assert contract.production(case,tmp_path)==case['expected']
    assert case==original

def test_original_failures_remain_recorded():
    fixture=contract.check_identity()
    assert len(fixture['rows'])==205 and sum(r['original_failure'] for r in fixture['rows'])==120

def test_complete_promotion_requires_all_export_and_caption_cases():
    from reproducibility.run import inventory
    keys={r['key'] for r in contract.cases()}
    capabilities={'PyFLASH.stats.results_to_excel','PyFLASH.stats.print_comparison_results'}
    complete={r['capability']:r for r in inventory(keys) if r['capability'] in capabilities}
    assert len(complete)==2 and all(r['status']=='validated-complete-contract' for r in complete.values())
    assert all(r['kind'].startswith('functional-') for r in complete.values())
    for capability,row in complete.items():
        missing=row['executed_subcontracts'].split(';')[0]
        assert next(r for r in inventory(keys-{missing}) if r['capability']==capability)['status']!='validated-complete-contract'

@pytest.mark.parametrize('verbose',[False,True])
def test_export_confirmation_obeys_the_requested_verbosity(tmp_path,monkeypatch,verbose):
    from PyFLASH import stats
    messages=[];monkeypatch.setattr(stats._log,'confirm',messages.append)
    stats.results_to_excel({'Declared':[2.5,.01]}, {}, tmp_path, 'report', verbose=verbose)
    assert messages==([f'Stats results saved to {tmp_path/"report.csv"}'] if verbose else [])
