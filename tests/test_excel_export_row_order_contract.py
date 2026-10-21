import importlib.util
import shutil
import pytest
from reproducibility import excel_export_contract as contract


@pytest.fixture(scope='module', autouse=True)
def authentic_original_workbooks():
    contract.check_identity()


@pytest.mark.parametrize('row', contract.cases(), ids=lambda row: row['key'])
def test_actual_spreadsheet_rows_preserve_supplied_group_order_and_input(row, tmp_path):
    assert contract.agrees(row, contract.production(row, tmp_path))


@pytest.mark.parametrize('name', [
    'source-manifest.json',
    'excel-index-functional-before-20261007-v1/frozen-before.json',
])
def test_changed_original_spreadsheet_evidence_refuses_before_export(tmp_path, monkeypatch, name):
    spec = importlib.util.spec_from_file_location('isolated_excel_evidence', contract.__file__)
    isolated = importlib.util.module_from_spec(spec); spec.loader.exec_module(isolated)
    archive = tmp_path / 'archive'; shutil.copytree(contract.ARCHIVE, archive)
    target = archive / name; target.write_bytes(target.read_bytes() + b'\n')
    isolated.ARCHIVE = archive
    monkeypatch.setattr(isolated, 'production', lambda *_: pytest.fail('Changed evidence reached export'))
    with pytest.raises(ValueError, match='evidence'):
        isolated.validate(tmp_path / 'output')


@pytest.mark.parametrize('method', [
    'export_IF_summary_excel', 'export_unregistered_summary_excel', 'export_behavior_summary_excel',
])
def test_changed_emitted_measurement_order_fails_original_contract(tmp_path, monkeypatch, method):
    from PyFLASH import batch
    original = batch._grouped_column_table

    def reversed_rows(groups, column):
        return original(groups, column).iloc[::-1].reset_index(drop=True)

    monkeypatch.setattr(batch, '_grouped_column_table', reversed_rows)
    row = next(row for row in contract.cases()
               if row['method'] == method and row['order'] == 'AB' and not row['missing'])
    assert not contract.agrees(row, contract.production(row, tmp_path))
