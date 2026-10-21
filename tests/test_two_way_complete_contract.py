"""Whole factorial reports, matrix directions, common scope and exact category ranks."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
import pandas as pd
from reproducibility import two_way_contract as contract

@pytest.mark.parametrize('case',contract.cases()+contract.matrix_cases(),ids=lambda r:r['key'])
def test_complete_two_factor_and_matrix_outputs_match_frozen_answers(case):
    before=deepcopy(case)
    assert contract.equal(contract.production(case),case['expected'])
    assert case==before

def test_all_original_failures_and_answers_remain_retained():
    fixture=contract.check_identity()
    assert len(fixture['rows'])==394 and len(fixture['matrix_rows'])==26
    assert sum(r['original_failure'] for r in fixture['rows'])==318
    assert sum(r['original_failure'] for r in fixture['matrix_rows'])==4

def test_invalid_factor_or_comparison_request_precedes_inference(monkeypatch):
    from PyFLASH import stats
    def forbidden(*args,**kwargs):raise AssertionError('Inference preceded validation')
    monkeypatch.setattr(stats,'_two_way_inference',forbidden);monkeypatch.setattr(stats,'_run_tukey',forbidden)
    frame=pd.DataFrame({'Condition':['A','A','B','B'],'FactorA':['L','H','L','H'],'FactorB':['M','F','M','F'],'Marker':[1,2,3,4]})
    experiment=SimpleNamespace(summary=frame,condition_list=[SimpleNamespace(name=n) for n in ('A','B')])
    for options in ({'factors':['FactorA'],'comparisons':['1-2']},{'factors':['FactorA','FactorA'],'comparisons':['1-2']},{'factors':['FactorA','FactorB'],'comparisons':['0-2']}):
        initial={}
        with pytest.raises(ValueError):stats.runTWA(experiment,'Marker',results_dict=initial,**options)
        assert initial=={}

def test_whole_parent_needs_every_matrix_cell_and_external_witness():
    from reproducibility.run import inventory
    from reproducibility.two_way_validation import required_keys
    keys=required_keys();capability='PyFLASH.stats.runTWA'
    assert next(r for r in inventory(keys) if r['capability']==capability)['status']=='validated-complete-contract'
    for missing in ('two-way.complete.0','two-way-tukey-matrix.ordinary.0','two-way-range.ordinary.0.1','two-way.native.ordinary'):
        assert next(r for r in inventory(keys-{missing}) if r['capability']==capability)['status']!='validated-complete-contract'

def test_a_changed_frozen_factor_answer_fails_identity(monkeypatch,tmp_path):
    import json
    fixture=json.loads(contract.FIXTURE.read_text());fixture['rows'][0]['expected']['method']='Changed'
    path=tmp_path/'changed.json';path.write_text(json.dumps(fixture));monkeypatch.setattr(contract,'FIXTURE',path)
    with pytest.raises(ValueError,match='differ from frozen'):contract.check_identity()
