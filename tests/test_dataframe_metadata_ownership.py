"""Measurement metadata must match its supplied identity without losing rows."""
import shutil
import pytest
from reproducibility import dataframe_metadata_contract as reference


@pytest.mark.parametrize('row',reference.cases(),ids=lambda row:row['key'])
def test_original_native_requested_metadata_and_complete_cells(row,tmp_path):
    assert reference.equal(reference.production(row,tmp_path),reference.expected(row))


@pytest.mark.parametrize('name',['run.json','probe-producer.py','source-manifest.json'])
def test_changed_original_metadata_evidence_is_refused(name,tmp_path,monkeypatch):
    archive = tmp_path/'archive'
    shutil.copytree(reference.ARCHIVE,archive)
    path = archive/name
    path.write_bytes(path.read_bytes()+b' ')
    monkeypatch.setattr(reference,'ARCHIVE',archive)
    with pytest.raises(ValueError,match='Original measurement metadata'):
        reference.check_identity()
