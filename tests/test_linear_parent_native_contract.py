"""Native scientific tables cover the actual public pipeline, with partial scope."""
from copy import deepcopy
import json
import pytest
from reproducibility import linear_parent_contract as contract

@pytest.mark.parametrize('row',contract.cases(),ids=lambda row:row['case']['key'])
def test_public_linear_tables_match_original_native_fits_and_corrections(row):
    before=deepcopy(row)
    assert contract.equal(contract.observe(row['case']),row['expected'])
    assert row==before

def test_native_answer_tampering_fails_identity(monkeypatch,tmp_path):
    fixture=json.loads(contract.FIXTURE.read_text(encoding='utf-8'))
    fixture['rows'][0]['expected']['y']['summary']['aic']+=1
    changed=tmp_path/'fixture.json';changed.write_text(json.dumps(fixture),encoding='utf-8')
    monkeypatch.setattr(contract,'FIXTURE',changed)
    with pytest.raises(ValueError,match='differ from original native'):contract.check_identity()

@pytest.mark.parametrize('row',contract.boundary_cases(),ids=lambda row:row['case']['key'])
def test_zero_outcome_intervals_match_original_independent_fits(row):
    before=deepcopy(row)
    assert contract.equal(contract.observe_zero_interval(row['case']),row['expected'])
    assert row==before

def test_partial_linear_science_does_not_certify_full_pipeline():
    from reproducibility.run import inventory
    fixture=contract.check_identity();assert fixture['complete_contract'] is False
    keys={'linear-parent-native.'+row['case']['key'] for row in contract.cases()+contract.boundary_cases()}
    keys.update('linear-wrapper-native.'+row['case']['key'] for row in contract.covariance_cases())
    for row in inventory(keys):
        if row['capability'] in contract.CAPABILITIES:assert row['status']!='validated-complete-contract'

def test_public_failure_is_retained_and_later_cases_continue(monkeypatch,tmp_path):
    original=contract.observe
    def fails_first(case):
        if case['key']==contract.cases()[0]['case']['key']:raise RuntimeError('Injected product failure')
        return original(case)
    monkeypatch.setattr(contract,'observe',fails_first)
    rows=contract.validate(tmp_path)
    assert rows[0]['status']=='disagree' and all(row['status']=='agree' for row in rows[1:])
    paired=json.loads((tmp_path/'linear-parent-native-paired.json').read_text(encoding='utf-8'))
    assert 'Injected product failure' in paired[0]['error']
    assert paired[0]['expected']==contract.cases()[0]['expected']

def test_broader_domain_answer_tampering_fails_identity(monkeypatch,tmp_path):
    fixture=json.loads(contract.FIXTURE.read_text(encoding='utf-8'))
    fixture['domain_rows'][0]['expected']['y']['means']['A']['adjusted_mean']+=1
    changed=tmp_path/'fixture.json';changed.write_text(json.dumps(fixture),encoding='utf-8')
    monkeypatch.setattr(contract,'FIXTURE',changed)
    with pytest.raises(ValueError,match='domain answers differ from original native'):contract.check_identity()


def test_HC1_reference_extension_preserves_all_approved_answers():
    fixture=contract.check_identity()
    root=contract.FIXTURE.parents[1]
    previous=json.loads((root/'reference-sources/linear-parent/HC1/before-HC1-reference.json').read_text(encoding='utf-8'))
    for key in ('rows','domain_rows','boundary_rows'):
        assert fixture[key]==previous[key]
    assert all(fixture['source_manifest'][name]==digest for name,digest in previous['source_manifest'].items())
    assert contract.check_HC1_reference(root,fixture)==122


def test_HC1_independent_probability_disagreement_is_rejected(tmp_path):
    fixture=json.loads(contract.FIXTURE.read_text(encoding='utf-8'))
    root=contract.FIXTURE.parents[1]
    for name,path in fixture['HC1_sources'].items():
        value=json.loads((root/path).read_text(encoding='utf-8'))
        if name=='original-results.json':
            value[0]['coefficients'][0]['routes']['aligned-HC1-normal']['p_value']+=.1
        (tmp_path/name).write_text(json.dumps(value),encoding='utf-8')
        fixture['HC1_sources'][name]=name
    with pytest.raises(ValueError,match='native coefficient answers disagree with original R'):
        contract.check_HC1_reference(tmp_path,fixture)


def test_robust_native_extension_preserves_approved_answers_and_scope():
    fixture=contract.check_identity();root=contract.FIXTURE.parents[1]
    previous=json.loads((root/'reference-sources/linear-parent/robust-estimatr/before-robust-reference.json').read_text(encoding='utf-8'))
    for key in ('rows','domain_rows','boundary_rows'):assert fixture[key]==previous[key]
    assert all(fixture['source_manifest'][name]==digest for name,digest in previous['source_manifest'].items())
    assert contract.check_robust_reference(root,fixture)==732
    assert fixture['complete_contract'] is False


@pytest.mark.parametrize('field',['covariance','fitted'])
def test_robust_native_complete_array_disagreement_is_rejected(tmp_path,field):
    fixture=json.loads(contract.FIXTURE.read_text(encoding='utf-8'));root=contract.FIXTURE.parents[1]
    for name,path in fixture['robust_sources'].items():
        value=json.loads((root/path).read_text(encoding='utf-8'))
        if name=='original-native-results.json':
            output=value['rows'][0]['output']
            if field=='covariance':node=output['values'][output['names'].index('covariance')]
            else:
                original=output['values'][output['names'].index('original')]
                node=original['values'][original['names'].index('fitted.values')]
            node['values'][0]+=1
        (tmp_path/name).write_text(json.dumps(value),encoding='utf-8');fixture['robust_sources'][name]=name
    (tmp_path/'original-R.json').write_text((root/fixture['native_path']).read_text(encoding='utf-8'),encoding='utf-8')
    fixture['native_path']='original-R.json'
    with pytest.raises(ValueError,match='robust '+field+' answers disagree with original R'):
        contract.check_robust_reference(tmp_path,fixture)


@pytest.mark.parametrize('field',['p_value','f_pvalue','q_value','p_adjusted'])
def test_tiny_positive_probabilities_cannot_be_approved_as_zero(field):
    assert not contract.equal({field:0.},{field:3.2596761993047113e-35})
    assert contract.equal({field:3.2596761993047113e-35},{field:3.2596761993047113e-35})


def test_stable_native_tail_extension_preserves_every_approved_answer():
    fixture=contract.check_identity();root=contract.FIXTURE.parents[1]
    previous=json.loads((root/'reference-sources/linear-parent/HC1-stable-tails/before-stable-tail-reference.json').read_text(encoding='utf-8'))
    for key in ('rows','domain_rows','boundary_rows'):assert fixture[key]==previous[key]
    for name,digest in previous['source_manifest'].items():assert fixture['source_manifest'][name]==digest
    assert fixture['probability_atol']==0


def test_expanded_stable_native_inference_preserves_answers_and_partial_scope():
    fixture=contract.check_identity();root=contract.FIXTURE.parents[1]
    previous=json.loads((root/'reference-sources/linear-parent/stable-native-inference/before-stable-native-inference.json').read_text(encoding='utf-8'))
    for key in ('rows','domain_rows','boundary_rows'):assert fixture[key]==previous[key]
    for name,digest in previous['source_manifest'].items():assert fixture['source_manifest'][name]==digest
    assert contract.check_stable_native_inference(root,fixture)==6046
    assert fixture['complete_contract'] is False


@pytest.mark.parametrize('kind',['coefficient','contrast','summary'])
def test_expanded_native_inference_rejects_zero_for_positive_probability(tmp_path,kind):
    fixture=json.loads(contract.FIXTURE.read_text(encoding='utf-8'));root=contract.FIXTURE.parents[1]
    for name,path in fixture['stable_inference_sources'].items():
        value=json.loads((root/path).read_text(encoding='utf-8'))
        if name=='original-results.json':
            row=value[0]
            if kind=='summary':row['summary']['f_pvalue']=0.
            else:next(iter(row['coefficients' if kind=='coefficient' else 'contrasts'].values()))['p_value']=0.
        (tmp_path/name).write_text(json.dumps(value),encoding='utf-8')
        fixture['stable_inference_sources'][name]=name
    with pytest.raises(ValueError,match='answers disagree with original R'):
        contract.check_stable_native_inference(tmp_path,fixture)


@pytest.mark.parametrize('row',contract.covariance_cases(),ids=lambda row:row['case']['key'])
def test_public_covariance_wrapper_complete_arrays_match_original_native_fit(row):
    assert contract.equal(contract.observe_covariance_wrapper(row['case']),row['wrapper_expected'])


def test_covariance_keyword_extension_preserves_all_previous_native_answers():
    fixture=contract.check_identity();root=contract.FIXTURE.parents[1]
    previous=json.loads((root/'reference-sources/linear-parent/covariance-keywords/before-covariance-keywords.json').read_text(encoding='utf-8'))
    for key in ('rows','domain_rows','boundary_rows'):assert fixture[key]==previous[key]
    for name,digest in previous['source_manifest'].items():assert fixture['source_manifest'][name]==digest
    assert contract.check_covariance_reference(root,fixture)==dict(native_fields=3160,correction_fields=280)
    assert fixture['complete_contract'] is False


@pytest.mark.parametrize('kind',['covariance','fitted','residual','probability'])
def test_covariance_independent_complete_output_disagreement_is_rejected(tmp_path,kind):
    fixture=json.loads(contract.FIXTURE.read_text(encoding='utf-8'));root=contract.FIXTURE.parents[1]
    for name,path in fixture['covariance_sources'].items():
        value=json.loads((root/path).read_text(encoding='utf-8'))
        if name=='comparisons':
            item=next(row for row in value if row['route']=='original-linearmodels' and (row['field']=='p_value' if kind=='probability' else row['kind']==kind))
            item['actual']=0. if kind=='probability' else item['actual']+1
        (tmp_path/(name+'.json')).write_text(json.dumps(value),encoding='utf-8')
        fixture['covariance_sources'][name]=name+'.json'
    with pytest.raises(ValueError,match='Covariance native .* answers disagree with original R'):
        contract.check_covariance_reference(tmp_path,fixture)


def test_covariance_corrected_native_probability_disagreement_is_rejected(tmp_path):
    fixture=json.loads(contract.FIXTURE.read_text(encoding='utf-8'));root=contract.FIXTURE.parents[1]
    for name,path in fixture['covariance_sources'].items():
        value=json.loads((root/path).read_text(encoding='utf-8'))
        if name=='pingouin':value[0]['adjusted'][0]=0.
        (tmp_path/(name+'.json')).write_text(json.dumps(value),encoding='utf-8')
        fixture['covariance_sources'][name]=name+'.json'
    with pytest.raises(ValueError,match='Covariance correction native answers disagree with original R'):
        contract.check_covariance_reference(tmp_path,fixture)
