"""Scientific identifiers and arbitrary metadata are literal Excel cells."""
import shutil
import pytest
from reproducibility import excel_literal_cell_contract as reference


@pytest.mark.parametrize('row', reference.cases(), ids=lambda row: row['key'])
def test_native_literal_cells_survive_every_public_batch_export_route(row, tmp_path):
    observed = reference.observe(row, tmp_path)
    assert observed['inputs_unchanged']
    assert not observed['disagreements'], observed['disagreements']


@pytest.mark.parametrize('name', ['client-reference.json', 'reference-producer.py', 'source-manifest.json'])
def test_changed_predeclared_literal_answers_are_refused(name, tmp_path, monkeypatch):
    archive = tmp_path/'archive'
    shutil.copytree(reference.ARCHIVE, archive)
    path = archive/name
    path.write_bytes(path.read_bytes()+b' ')
    monkeypatch.setattr(reference, 'ARCHIVE', archive)
    with pytest.raises(ValueError, match='Original literal Excel cells'):
        reference.check_identity()


def test_all_27_original_literal_and_missing_identity_failures_are_retained():
    assert reference.check_original_failures()['disagreements'] == 27

