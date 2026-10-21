"""Preserve measured means and authenticate the reasoned wording amendment."""
from copy import deepcopy
import json
import shutil
import pytest
from reproducibility import excel_mean_wording_semantics_contract as reference


@pytest.mark.parametrize('row',reference.cases(),ids=lambda row:row['key'])
def test_actual_means_and_display_meanings_agree(row,tmp_path):
    actual,expected=reference.observe(row,tmp_path)
    assert actual==expected


@pytest.mark.parametrize('name',['declared-reference.json','paired.json','native-imagej.json','original-roi-controls/paired.json'])
def test_changed_original_mean_evidence_is_refused(name,tmp_path,monkeypatch):
    archive=tmp_path/'archive';shutil.copytree(reference.ARCHIVE,archive)
    path=archive/name;path.write_bytes(path.read_bytes()+b' ')
    monkeypatch.setattr(reference,'ARCHIVE',archive)
    with pytest.raises(ValueError):reference.check_identity()


def test_changed_expected_mean_is_refused_before_public_calls(tmp_path):
    row=deepcopy(reference.cases()[0]);row['fixture']['expected_pixel_mean']=37.5
    with pytest.raises(AssertionError,match='Declared mean-wording control changed'):
        reference.observe(row,tmp_path)
    assert not list(tmp_path.iterdir())


def test_original_wording_failures_and_correct_numerical_values_remain():
    reference.check_identity()
    paired=json.loads((reference.ARCHIVE/'paired.json').read_text(encoding='utf-8'))
    assert len(paired['pixel_controls'])==3 and all(row['agrees'] for row in paired['pixel_controls'])
    assert len(paired['display_controls'])==4 and all(not row['agrees'] for row in paired['display_controls'])
    roi=json.loads((reference.ARCHIVE/'original-roi-controls/paired.json').read_text(encoding='utf-8'))
    assert len(roi['rows'])==2 and all(row['numerical_agrees'] and not row['description_agrees'] for row in roi['rows'])


def test_mean_semantics_are_registered_as_support_without_whole_promotions():
    from reproducibility.validation_registry import FAMILIES
    assert FAMILIES['batch-excel-mean-wording-semantics']=='reproducibility.excel_mean_wording_semantics_contract'
    assert not reference.COMPLETE_CAPABILITIES
    assert len(reference.required_keys('PyFLASH.experiment.Experiment.createSummary'))==5
    assert len(reference.required_keys('PyFLASH.batch.Batch.export_extended_data_excel'))==3
    assert reference.required_keys('PyFLASH.batch.Batch.export_extra_summary_excel')==set()
