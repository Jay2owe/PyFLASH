"""Positive indicator labels cannot imply a fixed reversed threshold."""
from copy import deepcopy
import shutil
import pytest
from reproducibility import excel_positive_label_semantics_contract as reference

@pytest.mark.parametrize('row',reference.cases(),ids=lambda row:row['key'])
def test_positive_labels_match_numeric_thresholds_and_existing_flags(row):
    assert reference.observe(row)['agrees']

@pytest.mark.parametrize('name',['declared-reference.json','paired.json','source-manifest.json'])
def test_changed_original_semantic_evidence_is_refused(name,tmp_path,monkeypatch):
    archive=tmp_path/'archive';shutil.copytree(reference.ARCHIVE,archive)
    path=archive/name;path.write_bytes(path.read_bytes()+b' ')
    monkeypatch.setattr(reference,'ARCHIVE',archive)
    with pytest.raises(ValueError,match='Original positive-label semantics'):
        reference.check_identity()

def test_changed_threshold_answer_is_refused_before_call():
    row=deepcopy(reference.cases()[0]);row['expected'][0]=1
    with pytest.raises(AssertionError,match='Declared positive classification or label changed'):
        reference.observe(row)

def test_original_wrong_labels_remain_failed_and_authenticated():
    assert reference.check_original_failures()['label_disagreements']==10

def test_supporting_label_truth_cannot_certify_whole_marker_or_exporter():
    assert not reference.COMPLETE_CAPABILITIES
    assert len(reference.required_keys('PyFLASH.markers.Antibody.addColocData'))==10
