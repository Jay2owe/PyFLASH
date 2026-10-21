"""Frozen independent finite-null inference and calibration regressions."""
import hashlib,json,math
from pathlib import Path
import numpy as np
import pytest
from PyFLASH import stats_extra as se
from reproducibility import minp_contract as reference
from reproducibility.reference_runtime import values

FROZEN=json.loads(reference.FIXTURE.read_text(encoding='utf-8'))

@pytest.mark.parametrize('row',FROZEN['rows'],ids=lambda row:row['key'])
def test_complete_minp_and_selected_calibration_answers(row):
    expected=values(row['expected'])
    np.testing.assert_allclose(reference.reference(row),expected,rtol=1e-9,atol=1e-12,equal_nan=True)
    np.testing.assert_allclose(reference.production(row),expected,rtol=1e-9,atol=1e-12,equal_nan=True)
    if row['key'].startswith('calibration.'):
        # Cutoffs must preserve the exact side of an empirical mass jump.
        actual=reference.production(row)
        if math.isnan(expected[0]):assert math.isnan(actual[0])
        else:assert actual[0]==expected[0]
        assert actual[1]<=row['parameters']['alpha']

def test_reference_identity_and_all_native_frozen_answers():
    assert hashlib.sha256(Path(reference.__file__).read_text(encoding='utf-8').encode()).hexdigest()==FROZEN['reference_code_sha256']
    assert reference.cases()==[{key:row[key] for key in reference.cases()[i]} for i,row in enumerate(FROZEN['rows'])]
    by_key={row['key']:values(row) for row in FROZEN['native']['rows']}
    for row in FROZEN['rows']:
        np.testing.assert_allclose(by_key[row.get('reference_key',row['key'])],values(row['expected']),rtol=1e-9,atol=1e-12,equal_nan=True)

@pytest.mark.parametrize('pair',[(0.5,1),(True,1),(0,0),(-1,1),(0,1,2),(0,'1')])
def test_invalid_comparison_identity_cannot_select_a_different_null_column(pair):
    null={'p':[[.1,.4],[.3,.7]],'pairs':[(0,1),(0,2)],'mode':'sampled'}
    with pytest.raises(ValueError):se.westfall_young_from_null([.2],null,[pair])

def test_duplicate_declared_pair_cannot_silently_overwrite_a_null_column():
    null={'p':[[.1,.4]],'pairs':[(0,1),(1,0)]}
    with pytest.raises(ValueError):se.westfall_young_from_null([.2,.3],null)

@pytest.mark.parametrize('p,null',[
    ([[.2]],{'p':[[.1]]}),([-.1],{'p':[[.1]]}),([1.1],{'p':[[.1]]}),
    ([math.inf],{'p':[[.1]]}),([.2],{'p':[]}),([.2],{'p':[.1]}),
    ([.2],{'p':[[math.nan]]}),([.2],{'p':[[math.inf]]}),([.2],{'p':[[1.1]]}),
    ([.2],{'p':[[.1]],'mode':'approximate'}),([.2,.3],{'p':[[.1]]})])
def test_invalid_supplied_distributions_fail_explicitly(p,null):
    with pytest.raises(ValueError):se.westfall_young(p,null)

@pytest.mark.parametrize('alpha',[-.1,1.1,math.nan,math.inf,'bad',None])
def test_invalid_alpha_fails_before_sampling(alpha,monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('sampling started')
    monkeypatch.setattr(se,'permutation_null',forbidden)
    with pytest.raises(ValueError):se.correction_audit([.2],(3,3),alpha=alpha)

@pytest.mark.parametrize('count',[0,3,2.,True])
def test_inconsistent_permutation_count_is_not_reported_as_resolution(count):
    null={'p':[[.1],[.3]],'pairs':[(0,1)],'n_perm':count,'mode':'sampled'}
    with pytest.raises(ValueError):se.correction_audit([.2],null=null)

def test_generators_are_consumed_once_and_sampling_metadata_survives_alignment():
    null={'p':[[.4,.3],[.6,.7]],'pairs':[(0,2),(0,1)],'mode':'sampled','n_perm':2}
    assert se.westfall_young((v for v in [.01,.02]),null)==[1/3,1/3]
    assert se.westfall_young_from_null([.01,.02],null,[(0,1),(0,2)])==[1/3,1/3]
    audit=se.correction_audit((v for v in [.01,.02]),null=null,pairs=[(0,1),(0,2)])
    assert audit['westfall_young']==[1/3,1/3]
    assert audit['permutation']['p_resolution']==1/3
    assert audit['permutation']['alpha_star'] is None

def test_missing_observed_comparisons_are_not_a_zero_error_rate():
    null={'p':[[math.nan],[math.nan]],'pairs':[(0,1)],'mode':'exact','n_perm':2}
    audit=se.correction_audit([math.nan],null=null)
    assert math.isnan(audit['westfall_young'][0])
    assert audit['permutation'] is None
    assert 'no finite observed' in audit['skipped']

def test_missing_observed_column_does_not_poison_retained_family_calibration():
    null={'p':[[math.nan,.1],[math.nan,.3]],'pairs':[(0,1),(0,2)],'mode':'sampled','n_perm':2}
    audit=se.correction_audit([math.nan,.2],null=null,alpha=.5)
    assert math.isnan(audit['westfall_young'][0])
    assert audit['westfall_young'][1]==2/3
    assert audit['permutation']['alpha_bonferroni']==.5
    assert audit['permutation']['p_floor']==.1

def test_unattainable_threshold_survives_results_and_verdict_export():
    from PyFLASH.stats import _audit_to_results_dict
    null={'p':[[.3],[.6]],'pairs':[(0,1)],'mode':'sampled','n_perm':2}
    audit=se.correction_audit([.01],null=null)
    assert 'calibrated' not in se.verdict_changes(audit)['1']
    results={};strings={}
    _audit_to_results_dict(audit,['one comparison'],results,strings)
    assert 'unattainable' in strings['Correction calibration']
    assert 'Correction-WestfallYoung' in results

def test_exact_rank_separation_has_no_fictitious_positive_cutoff():
    parameters={'group_sizes':[2,2],'ranks':[1.5,1.5,3.5,3.5],'statistic':'conover'}
    null=se.permutation_null(**parameters)
    assert null['p'][0,0]==null['p'][-1,0]==0.
    audit=se.correction_audit([.01],**parameters)
    assert audit['permutation']['alpha_star'] is None
    assert audit['permutation']['p_floor']==0.
