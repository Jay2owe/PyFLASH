"""Whole one-way reports, options, styles, order and retained before answers."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from reproducibility import one_way_contract as contract

@pytest.mark.parametrize('case',contract.cases(),ids=lambda row:row['key'])
def test_complete_report_against_independent_before_answers(case):
    original=deepcopy(case)
    assert contract.equal(contract.production(case),case['expected'])
    assert case==original

def test_before_failures_and_all_numerical_answers_remain_archived():
    fixture=contract.check_identity()
    assert len(fixture['rows'])==1017
    previous=json.loads((Path(contract.__file__).parent/fixture['prior_reference']).read_text())
    assert sum(r['original_failure'] for r in previous['rows'])==423
    before=json.loads((Path(contract.__file__).parent/fixture['before_rounds'][0]).read_text())
    assert len(before['rows'])==1347 and sum(r['original_failure'] for r in before['rows'])==337

def test_changed_answer_cannot_replace_unchanged_before_evidence(tmp_path,monkeypatch):
    fixture=json.loads(contract.FIXTURE.read_text())
    fixture['rows'][0]['expected']={'tampered':True}
    changed=tmp_path/'changed.json';changed.write_text(json.dumps(fixture))
    monkeypatch.setattr(contract,'FIXTURE',changed)
    with pytest.raises(ValueError,match='frozen before-correction'):contract.check_identity()

def test_invalid_request_has_no_inference_or_report_mutation(monkeypatch):
    from PyFLASH import stats
    def forbidden(*args,**kwargs):raise AssertionError('Inference preceded request validation')
    monkeypatch.setattr(stats,'_one_way_geometry',forbidden,raising=False)
    for groups in ([[1,2,3],[2,4,6]], [[],[]]):
        for options in ({'comparisons':['0-2']},{'comparisons':['1-2'],'posthoc_correction':'made-up'}):
            raw={'caller':'preserved'}
            with pytest.raises(ValueError):stats.runOWA(groups,results_dict=raw,**options)
            assert raw=={'caller':'preserved'}

def test_parent_promotion_requires_every_full_report_and_native_witness():
    from reproducibility.run import inventory
    from reproducibility.one_way_validation import required_keys
    keys=required_keys();capability='PyFLASH.stats.runOWA'
    assert next(r for r in inventory(keys) if r['capability']==capability)['status']=='validated-complete-contract'
    for missing in ('one-way.session.default-10000','one-way.extension.276','one-way-range.ordinary.0.1','studentized-range-tail.11'):
        assert next(r for r in inventory(keys-{missing}) if r['capability']==capability)['status']!='validated-complete-contract'
