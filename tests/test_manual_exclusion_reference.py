import json
from pathlib import Path
import pytest
from reproducibility import manual_exclusion_contract as contract


def test_every_declared_manual_request_has_one_literal_full_answer():
    contract.check_identity()
    rows=contract.cases()
    assert len(rows)==160 and len({row['key'] for row in rows})==160
    assert {row['api'] for row in rows}=={'apply_exclusions','mark_exclusions','exclude_animals',
        'mark_animals','exclude_subjects','mark_subjects','clear_exclusions'}
    assert all(contract.answer(row)==row['expected'] for row in rows)


@pytest.mark.parametrize('alteration',['answer','input','reference-hash'])
def test_changed_frozen_evidence_is_refused_before_production(tmp_path,monkeypatch,alteration):
    data=json.loads(contract.FIXTURE.read_text())
    if alteration=='answer':data['rows'][0]['expected']['frames']['CTX'][0][2]=999.
    elif alteration=='input':data['rows'][0]['options']['subjects']=['different subject']
    else:data['reference_sha256']='0'*64
    fixture=tmp_path/'changed.json';fixture.write_text(json.dumps(data))
    monkeypatch.setattr(contract,'FIXTURE',fixture)
    monkeypatch.setattr(contract,'production',lambda *args:pytest.fail('Changed evidence reached production.'))
    with pytest.raises(ValueError):contract.validate(tmp_path/'execution')


def test_one_failed_request_keeps_later_requests_and_exact_paired_answers(tmp_path,monkeypatch):
    cases=contract.cases()[:3]
    monkeypatch.setattr(contract,'check_identity',lambda:None)
    monkeypatch.setattr(contract,'cases',lambda:cases)
    calls=[]
    def production(case,output):
        calls.append(case['key'])
        if len(calls)==2:raise RuntimeError('retained request failure')
        if len(calls)==3:
            earlier=json.loads((tmp_path/'manual-exclusion-paired-data.json').read_text())
            assert len(earlier['rows'])==2 and not earlier['rows'][1]['agrees']
        return contract.answer(case)
    monkeypatch.setattr(contract,'production',production)
    rows=contract.validate(tmp_path)
    assert calls==[case['key'] for case in cases]
    assert [row['status'] for row in rows]==['agree','disagree','agree']
    paired=json.loads((tmp_path/'manual-exclusion-paired-data.json').read_text())
    assert paired['rows'][1]['error']=='RuntimeError: retained request failure'
    assert paired['rows'][0]['production']==cases[0]['expected']


def test_unknown_region_metadata_is_not_silently_dropped(tmp_path):
    case=contract.cases()[0]
    actual=contract.production(case,tmp_path/'one')
    expected=contract.answer(case)
    assert actual==expected
    assert actual['ledger_regions']==['CTX','CTX']


@pytest.mark.parametrize('alteration',['handoff-input','stacked-input','region-answer'])
def test_region_evidence_cannot_be_changed_without_a_reviewed_revision(tmp_path,monkeypatch,alteration):
    data=json.loads(contract.FIXTURE.read_text())
    if alteration=='handoff-input':data['rows'][140]['options']['marked_roi']='different'
    elif alteration=='stacked-input':data['rows'][-1]['options']['order'].reverse()
    else:data['rows'][140]['expected']['ledger_regions']=['wrong']
    fixture=tmp_path/'changed.json';fixture.write_text(json.dumps(data))
    monkeypatch.setattr(contract,'FIXTURE',fixture)
    monkeypatch.setattr(contract,'production',lambda *args:pytest.fail('Changed region evidence reached production.'))
    with pytest.raises(ValueError):contract.validate(tmp_path/'execution')


def test_joint_requests_gate_both_the_marker_and_the_application():
    for case in contract.cases():
        owners=contract.owners(case)
        assert contract.capability(case) in owners
        if case.get('kind')=='handoff':
            assert owners==('PyFLASH.exclusions.apply_exclusions','PyFLASH.exclusions.'+case['options']['marked_api'])
        elif case.get('kind')=='stacked':
            assert owners==('PyFLASH.exclusions.apply_exclusions','PyFLASH.exclusions.mark_exclusions')
