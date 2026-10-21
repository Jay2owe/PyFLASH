"""Actual workbook values must survive equivalent include/exclude containers."""
import pytest
from reproducibility import excel_export_contract as reference


@pytest.fixture(scope='module', autouse=True)
def authentic_literal_input_and_failure_identity():
    reference.check_identity()


@pytest.mark.parametrize('row', reference.typed_cases(), ids=lambda row: row['key'])
def test_public_workbook_values_preserve_equivalent_filter_container(row, tmp_path):
    assert reference.typed_agrees(row, reference.typed_production(row, tmp_path))


@pytest.mark.parametrize('row', [row for row in reference.typed_domain_cases()
    if not row.get('expected_refusal')], ids=lambda row: row['key'])
def test_empty_filter_collections_leave_literal_values_available(row, tmp_path):
    assert reference.typed_agrees(row, reference.typed_production(row, tmp_path))


@pytest.mark.parametrize('row', [row for row in reference.typed_domain_cases()
    if row.get('expected_refusal')], ids=lambda row: row['key'])
def test_invalid_regex_in_collection_is_refused_before_writing_a_workbook(row, tmp_path):
    actual = reference.typed_production(row, tmp_path)
    assert reference.typed_agrees(row, actual)
    assert actual['error'].startswith('ValueError: Invalid ' + row['target'] + ' regex')
    assert actual['workbook_cells'] == {}
    assert actual['output_names'] == []
    assert actual['inputs_unchanged']


@pytest.mark.parametrize('name', ['source-manifest.json', 'run.json', 'executed-input-and-reader-recipe.py'])
def test_changed_typed_input_evidence_is_refused(tmp_path, monkeypatch, name):
    import shutil
    archive = tmp_path / 'archive'
    shutil.copytree(reference.TYPED_ARCHIVE, archive)
    target = archive / name
    target.write_bytes(target.read_bytes() + b'\n')
    monkeypatch.setattr(reference, 'TYPED_ARCHIVE', archive)
    with pytest.raises(ValueError, match='evidence'):
        reference.check_identity()
