"""Raw/mean physical ratio units and retained evidence cannot silently change."""
from copy import deepcopy
import shutil
import pytest
from reproducibility import surface_volume_unit_contract as reference


@pytest.mark.parametrize('row',reference.cases(),ids=lambda row:row['key'])
def test_every_surface_volume_ratio_mean_and_unit_label_agrees(row,tmp_path):
    actual,expected=reference.observe(row,tmp_path)
    assert reference.agrees(row,actual,expected)


@pytest.mark.parametrize('name',['declared-reference.json','native-imagej.json','paired.json',
    'surface-volume-unit-amendment.json','original-private-failure/run.json','qualified-private/run.json'])
def test_modified_unit_evidence_is_refused(name,tmp_path,monkeypatch):
    archive=tmp_path/'archive';shutil.copytree(reference.ARCHIVE,archive)
    target=archive/name;target.write_bytes(target.read_bytes()+b' ')
    monkeypatch.setattr(reference,'ARCHIVE',archive)
    with pytest.raises(ValueError):reference.check_identity()


def test_changed_ratio_answer_is_refused_before_public_calls(tmp_path):
    row=deepcopy(reference.cases()[0]);row['control']['expected_mean']+=1.
    with pytest.raises(AssertionError,match='Declared surface/volume'):reference.observe(row,tmp_path)
    assert not list(tmp_path.iterdir())


def test_unit_family_never_promotes_whole_summaries_or_exporters():
    from reproducibility.validation_registry import FAMILIES
    assert FAMILIES['surface-volume-unit-semantics']=='reproducibility.surface_volume_unit_contract'
    assert not reference.COMPLETE_CAPABILITIES
    assert len(reference.required_keys('PyFLASH.experiment.Experiment.createSummary'))==7
    assert reference.required_keys('PyFLASH.experiment.Experiment.processData')==set()


def test_original_correct_numbers_and_missing_units_remain_retained():
    import json
    reference.check_identity()
    proof=json.loads((reference.ARCHIVE/'run.json').read_text(encoding='utf-8'))
    assert proof['numerical_disagreements']==0 and proof['display_disagreements']==2
    failure=json.loads((reference.ARCHIVE/'original-private-failure/run.json').read_text(encoding='utf-8'))
    recovery=json.loads((reference.ARCHIVE/'qualified-private/run.json').read_text(encoding='utf-8'))
    assert not failure['passed'] and failure['disagreements']==7
    assert recovery['passed'] and recovery['comparisons']==226 and recovery['disagreements']==0
    assert recovery['reused_candidate_comparisons']==0
