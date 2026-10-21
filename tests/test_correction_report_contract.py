"""Independently frozen complete correction reports, including caller metadata."""
import hashlib,json
from pathlib import Path
import pytest
from PyFLASH import stats_extra as se
from reproducibility import correction_report_contract as reference

FROZEN=json.loads(reference.FIXTURE.read_text(encoding='utf-8'))
ROWS=FROZEN['rows']
NATIVE={row['key']:row for row in FROZEN['native']['rows']}

@pytest.mark.parametrize('row',ROWS,ids=lambda row:row['key'])
def test_every_report_field_and_verdict_against_both_independent_references(row):
    expected=reference.decoded(row['expected'])
    reference.complete_equal(reference.reference(row,all_rows=ROWS),expected)
    reference.complete_equal(reference.native_result(NATIVE[row['key']]),expected)
    reference.complete_equal(reference.production(row,all_rows=ROWS),expected)

def test_frozen_reference_identity_and_original_answers_remain_intact():
    assert hashlib.sha256(Path(reference.__file__).read_text(encoding='utf-8').encode()).hexdigest()==FROZEN['reference_code_sha256']
    assert reference.dependency_identities()==FROZEN['dependencies']
    reference.check_dependency_lineage(FROZEN)
    assert reference.cases()==[{key:row[key] for key in case} for case,row in zip(reference.cases(),ROWS,strict=True)]
    preceding=reference.FIXTURE.with_name('correction_report_reference_v3.json')
    preceding_revision=json.loads(preceding.read_text(encoding='utf-8'))
    assert hashlib.sha256(preceding.read_bytes()).hexdigest()==FROZEN['previous_fixture_sha256']
    assert preceding_revision['rows']==ROWS
    assert preceding_revision['native']==FROZEN['native']
    middle=reference.FIXTURE.with_name('correction_report_reference_v2.json')
    metadata_revision=json.loads(middle.read_text(encoding='utf-8'))
    assert hashlib.sha256(middle.read_bytes()).hexdigest()==preceding_revision['previous_fixture_sha256']
    old=reference.FIXTURE.with_name('correction_report_reference.json')
    previous=json.loads(old.read_text(encoding='utf-8'))
    assert hashlib.sha256(old.read_bytes()).hexdigest()==metadata_revision['previous_fixture_sha256']
    assert metadata_revision['rows']==ROWS
    assert metadata_revision['native']==FROZEN['native']==previous['native']
    assert [row['expected'] for row in previous['rows']]==[row['expected'] for row in ROWS]
    assert len(ROWS)==len(NATIVE)==577

def test_deadline_revision_cannot_change_a_frozen_answer():
    from copy import deepcopy
    changed=deepcopy(FROZEN)
    changed['rows'][0]['expected']={'changed':'answer'}
    with pytest.raises(ValueError,match='inputs, answers or native results changed'):
        reference.check_dependency_lineage(changed)

def test_deadline_revision_cannot_change_underlying_value_null(monkeypatch,tmp_path):
    payload=json.loads(reference.values_reference.FIXTURE.read_text(encoding='utf-8'))
    payload['rows'][0]['expected']['values'][0]=987654321
    changed=tmp_path/'changed-value.json';changed.write_text(json.dumps(payload))
    monkeypatch.setattr(reference.values_reference,'FIXTURE',changed)
    with pytest.raises(ValueError,match='numerical evidence changed'):
        reference.check_dependency_lineage(FROZEN)

@pytest.mark.parametrize('comparisons',[['same','same'],[1,'1'],['2']])
def test_a_verdict_cannot_drop_a_comparison_with_a_duplicate_display_name(comparisons):
    audit={'uncorrected':[.01,.2],'holm':[.02,.2],'permutation':None}
    with pytest.raises(ValueError):se.verdict_changes(audit,comparisons)

@pytest.mark.parametrize('alpha',[-.1,1.1,float('nan'),float('inf'),None,'bad'])
def test_invalid_verdict_threshold_cannot_report_misleading_significance(alpha):
    with pytest.raises(ValueError):se.verdict_changes({'uncorrected':[.01]},alpha=alpha)
