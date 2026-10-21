"""Every pair keeps its requested group, order, probability and report fields."""
from copy import deepcopy
from pathlib import Path
import json
import pytest
from reproducibility import mann_whitney_contract as contract
from reproducibility import mann_whitney_validation as validation

@pytest.mark.parametrize('case',contract.cases(),ids=lambda row:row['key'])
def test_complete_rank_sum_report_against_frozen_reference(case):
    original=deepcopy(case)
    assert contract.equal(contract.production(case['parameters']),case['expected'])
    assert case==original

def test_original_83_failures_remain_preserved():
    fixture=contract.check_identity()
    assert len(fixture['rows'])==247 and sum(r['original_failure'] for r in fixture['rows'])==83

@pytest.mark.parametrize('case',[r for r in validation.native_cases() if r['role']=='independent-native-corroboration'],ids=lambda r:r['query']['key'])
def test_native_answers_remain_preserved(case):
    directory=Path(contract.__file__).parent/'reference-sources/mann-whitney'
    source='mann-whitney-tail-native-confirmed-mann-whitney-tail-symmetry-results.json' if case['query']['key'].endswith('.reverse-stable-tail') else 'mann-whitney-native-confirmed-mann-whitney-results.json'
    payload=json.loads((directory/source).read_text())
    from reproducibility.reference_runtime import values
    row=next(r for r in payload['rows'] if r['key']==case['query']['key'])
    assert validation.native_equal(values(row),case['expected'])

def test_every_report_and_native_witness_is_required_for_complete_promotion():
    from reproducibility.run import inventory
    key='PyFLASH.stats.mwu_multiple_comparisons'
    contracts={r['key'] for r in contract.cases()}|{r['query']['key'] for r in validation.native_cases() if r['role']=='independent-native-corroboration'}
    complete=next(r for r in inventory(contracts) if r['capability']==key)
    assert complete['status']=='validated-complete-contract'
    for missing in ('mwu.complete.empty-middle.1.ns','mwu-native.22.reverse-stable-tail'):
        assert next(r for r in inventory(contracts-{missing}) if r['capability']==key)['status']!='validated-complete-contract'

def test_invalid_later_pair_is_rejected_before_inference_or_report_mutation(monkeypatch):
    from PyFLASH import stats
    def forbidden(*args,**kwargs):raise AssertionError('Inference started before pair validation')
    monkeypatch.setattr(stats.stats,'mannwhitneyu',forbidden)
    raw={'caller':{'retained':[1,2]}};original=deepcopy(raw)
    with pytest.raises(ValueError):stats.mwu_multiple_comparisons([[1.,2.],[3.,4.]],['1-2','2-9'],raw)
    assert raw==original
