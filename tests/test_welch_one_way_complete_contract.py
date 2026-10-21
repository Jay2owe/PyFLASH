"""Weighted ANOVA, posthoc fields, undefined designs and complete preflight."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from reproducibility import welch_one_way_contract as contract

@pytest.mark.parametrize('case',contract.cases(),ids=lambda row:row['key'])
def test_complete_report_against_independent_before_answers(case):
    original=deepcopy(case)
    assert contract.equal(contract.production(case),case['expected'])
    assert case==original

def test_all_original_failures_remain_archived():
    fixture=contract.check_identity()
    assert len(fixture['rows'])==330
    previous=json.loads((Path(contract.__file__).parent/fixture['prior_reference']).read_text())
    assert sum(r['original_failure'] for r in previous['rows'])==145

def test_invalid_requests_never_infer_or_change_a_report(monkeypatch):
    from PyFLASH import stats
    def forbidden(*args,**kwargs):raise AssertionError('Inference preceded request validation')
    monkeypatch.setattr(stats,'_welch_one_way_geometry',forbidden,raising=False)
    for groups in ([[1,2,3],[2,4,6]],[[],[]]):
        for options in ({'comparisons':['0-2']},{'comparisons':['1-2'],'posthoc':'made-up'}):
            raw={'caller':'preserved'}
            with pytest.raises(ValueError):stats.runWelchOWA(groups,results_dict=raw,**options)
            assert raw=={'caller':'preserved'}

def test_whole_parent_needs_every_report_and_native_field_witness():
    from reproducibility.run import inventory
    from reproducibility.welch_one_way_validation import required_keys
    keys=required_keys();capability='PyFLASH.stats.runWelchOWA'
    assert next(r for r in inventory(keys) if r['capability']==capability)['status']=='validated-complete-contract'
    for missing in ('welch-one-way.complete.0','welch-range.ordinary.0.1',next(k for k in keys if k.startswith('anova-fields.native.'))):
        assert next(r for r in inventory(keys-{missing}) if r['capability']==capability)['status']!='validated-complete-contract'
