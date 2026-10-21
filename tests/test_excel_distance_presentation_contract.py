"""Distance summary aliases retain physical units and immutable failed controls."""
from copy import deepcopy
import json
import shutil
import pytest
from reproducibility import excel_distance_presentation_contract as reference

@pytest.mark.parametrize('row',reference.cases(),ids=lambda row:row['key'])
def test_public_distance_summary_and_presentation_agree(row,tmp_path):
    actual,expected=reference.observe(row,tmp_path)
    assert actual==expected

@pytest.mark.parametrize('name',['declared-reference.json','paired.json','native-imagej.json','amended-reference.json','original-unit-closure/run.json'])
def test_changed_distance_evidence_is_refused(name,tmp_path,monkeypatch):
    archive=tmp_path/'archive';shutil.copytree(reference.ARCHIVE,archive)
    path=archive/name;path.write_bytes(path.read_bytes()+b' ')
    monkeypatch.setattr(reference,'ARCHIVE',archive)
    with pytest.raises(ValueError):reference.check_identity()

def test_changed_distance_expected_answer_is_refused_before_public_calls(tmp_path):
    row=deepcopy(reference.cases()[0]);row['fixture']['expected_mean_um']=2.
    with pytest.raises(AssertionError,match='Declared distance presentation changed'):reference.observe(row,tmp_path)
    assert not list(tmp_path.iterdir())

def test_original_correct_distance_and_three_display_failures_are_preserved():
    reference.check_identity()
    paired=json.loads((reference.ARCHIVE/'paired.json').read_text(encoding='utf-8'))
    assert paired['numerical_control']==dict(actual=4.,expected=4.,agrees=True)
    assert len(paired['display_controls'])==3 and all(not row['agrees'] for row in paired['display_controls'])
    assert paired['display_controls'][0]['error'].startswith('KeyError:')
    units=json.loads((reference.ARCHIVE/'original-unit-closure/run.json').read_text(encoding='utf-8'))
    assert units['controls']==12 and units['failed']==5 and not units['passed']

def test_distance_support_family_has_no_whole_capability_promotions():
    from reproducibility.validation_registry import FAMILIES
    assert FAMILIES['batch-excel-distance-presentation']=='reproducibility.excel_distance_presentation_contract'
    assert not reference.COMPLETE_CAPABILITIES
    assert len(reference.required_keys('PyFLASH.experiment.Experiment.createSummary'))==1
    assert len(reference.required_keys('PyFLASH.batch.Batch.export_IF_summary_excel'))==5
    assert len(reference.required_keys('PyFLASH.batch.Batch.export_extra_summary_excel'))==3
    assert reference.required_keys('PyFLASH.batch.Batch.export_extended_data_excel')==set()

def test_modern_and_legacy_distance_aliases_share_one_description():
    from PyFLASH import export
    assert export.IF_NAME_MAP['<ab>_DistToVentricleMean'] is export.IF_NAME_MAP['<ab>_DistToVentricle']
