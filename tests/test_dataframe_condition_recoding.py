"""Original constructor/marker cells must receive their condition mapping once."""
import shutil
import pytest
from reproducibility import dataframe_recoding_contract as reference


@pytest.mark.parametrize('row', reference.cases(), ids=lambda row: row['key'])
def test_original_native_recoding_and_complete_measurement_cells(row, tmp_path):
    assert reference.production(row, tmp_path) == reference.expected(row)


@pytest.mark.parametrize('name', ['run.json', 'probe-producer.py', 'source-manifest.json'])
def test_modified_original_native_evidence_is_refused(name, tmp_path, monkeypatch):
    archive = tmp_path / 'archive'
    shutil.copytree(reference.ARCHIVE, archive)
    path = archive / name
    path.write_bytes(path.read_bytes() + b' ')
    monkeypatch.setattr(reference, 'ARCHIVE', archive)
    with pytest.raises(ValueError, match='Original condition recoding'):
        reference.check_identity()
