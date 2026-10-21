"""Grouping paths honour declared comparisons and preserve all measurements."""
import pytest
import shutil
from reproducibility import dataframe_comparison_contract as reference


@pytest.mark.parametrize('row',reference.cases(),ids=lambda row:row['key'])
def test_public_grouping_paths_honour_literal_comparison_contract(row,tmp_path):
    assert reference.production(row,tmp_path)==reference.expected(row)


@pytest.mark.parametrize('name',['run.json','dataframe_comparison_contract.py','source-manifest.json'])
def test_original_comparison_answers_and_producers_cannot_change(name,tmp_path,monkeypatch):
    archive=tmp_path/'archive'
    shutil.copytree(reference.ARCHIVE,archive)
    path=archive/name
    path.write_bytes(path.read_bytes()+b' ')
    monkeypatch.setattr(reference,'ARCHIVE',archive)
    with pytest.raises(ValueError,match='Original comparison request'):
        reference.check_identity()


def test_a_changed_measurement_is_detected_even_when_pairs_match(tmp_path):
    row=next(row for row in reference.cases() if not row['refused'])
    actual=reference.production(row,tmp_path)
    actual['summary']['data'][0][2]=123.0
    assert actual!=reference.expected(row)
