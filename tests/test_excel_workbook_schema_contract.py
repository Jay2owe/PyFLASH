"""Metadata, descriptions and sidecars must be as reliable as measurements."""
from copy import deepcopy
from pathlib import Path
import shutil
import pytest
from reproducibility import excel_workbook_schema_contract as reference


@pytest.mark.parametrize('row', reference.cases(), ids=lambda row: row['key'])
def test_every_original_request_matches_all_workbook_cells_and_reports(row, tmp_path):
    observed = reference.observe(row, tmp_path)
    assert observed['inputs_unchanged']
    assert not observed['disagreements'], observed['disagreements']


@pytest.mark.parametrize('name', ['client-reference.json', 'reference-producer.py',
                                 'accepted-label-declarations.py', 'source-manifest.json'])
def test_changed_frozen_workbook_schema_is_refused(name, tmp_path, monkeypatch):
    archive = tmp_path / 'archive'
    shutil.copytree(reference.ARCHIVE, archive)
    path = archive / name
    path.write_bytes(path.read_bytes() + b' ')
    monkeypatch.setattr(reference, 'ARCHIVE', archive)
    with pytest.raises(ValueError, match='Original complete workbook schema'):
        reference.check_identity()


def one_summary_case():
    return next(row for row in reference.cases() if row['original_key'] ==
        'excel-orchestration.export_excel.flags-0010.absolute.one.False')


def test_original_report_convention_failures_and_every_scientific_cell_are_preserved():
    import json
    assert reference.check_original_failures()['disagreements'] == 16
    original = json.loads((reference.ARCHIVE.parent/'v1/client-reference.json').read_text(encoding='utf-8'))
    current = json.loads((reference.ARCHIVE.parent/'v2/client-reference.json').read_text(encoding='utf-8'))
    changed = 0
    for before, after in zip(original['rows'], current['rows']):
        assert {key: value for key, value in before.items() if key != 'expected_workbooks'} == {
            key: value for key, value in after.items() if key != 'expected_workbooks'}
        for old, new in zip(before['expected_workbooks'], after['expected_workbooks']):
            assert old['request'] == new['request']
            assert old['worksheets'] == new['worksheets']
            assert old['regex_report'].replace(' (did not match include regex)', ' (include)').replace(
                ' (matched exclude regex)', ' (exclude)') == new['regex_report']
        changed += before != after
    assert changed == 16


def test_native_empty_index_convention_preserves_all_records_and_other_cells():
    import json
    assert len(reference.check_empty_index_originals()) == 4
    old = json.loads((reference.ARCHIVE.parent/'v2/client-reference.json').read_text(encoding='utf-8'))
    current = reference.check_identity()
    changed = 0
    for before,after in zip(old['rows'],current['rows']):
        revised = deepcopy(before)
        for workbook in revised['expected_workbooks']:
            for sheet in workbook['worksheets']:
                if sheet['name'] == 'Extra Columns' and sheet['cells'] == [['Column','Display Name','Sheet'],[None,None,None]]:
                    sheet['cells'] = [['Column','Display Name','Sheet']]
        assert revised == after
        changed += before != after
    assert changed == 4
    controls = json.loads((reference.ARCHIVE/'native-empty-index-controls/run.json').read_text(encoding='utf-8'))
    assert controls['passed'] and len(controls['rows']) == 4
    assert {row['engine'] for row in controls['rows'] if row['supplied_blank'] is None} == {'openpyxl','xlsxwriter'}
    assert all(row['read_back_rows'] == [['Column','Display Name','Sheet']]
               for row in controls['rows'] if row['supplied_blank'] is None)


@pytest.mark.parametrize('field', ['conditions', 'overview', 'description', 'merges',
                                  'sheet-order', 'additional-sheet', 'report', 'formula', 'extra-row'])
def test_each_full_workbook_obligation_detects_changed_actual_output(field, tmp_path):
    row = one_summary_case()
    observed = reference.observe(row, tmp_path)
    assert not observed['disagreements']
    changed = deepcopy(observed)
    workbook = changed['workbooks'][0]
    sheets = workbook['worksheets']
    if field == 'conditions':
        sheets[0]['cells'][1][0] = 'Wrong group'
    elif field == 'overview':
        sheets[1]['cells'][1][3] = 'Undocumented metric'
    elif field == 'description':
        sheets[2]['cells'][-1][0] = 'Wrong units/method'
    elif field == 'merges':
        sheets[0]['merged_ranges'] = []
    elif field == 'sheet-order':
        sheets.reverse()
    elif field == 'additional-sheet':
        sheets.append(dict(name='Unexpected', cells=[['Unrequested']], merged_ranges=[], formula_cells=[]))
    elif field == 'report':
        workbook['regex_report'] = workbook['regex_report'].replace('Candidate summary columns: 1', 'Candidate summary columns: 999')
    elif field == 'formula':
        sheets[0]['formula_cells'] = ['B2']
    elif field == 'extra-row':
        sheets[2]['cells'].append([999, None, None])
    assert reference.evaluate(row, changed), field


def test_actual_corrupted_conditions_are_detected_without_changing_measurements(tmp_path, monkeypatch):
    from openpyxl import load_workbook
    from PyFLASH.batch import Batch
    original = Batch.export_excel

    def corrupt_metadata(batch, *args, **kwargs):
        paths = original(batch, *args, **kwargs)
        path = next(Path(path) for path in paths if path.endswith('.xlsx'))
        book = load_workbook(path)
        try:
            book['Experimental Conditions']['A2'] = 'Wrong group'
            book.save(path)
        finally:
            book.close()
        return paths

    monkeypatch.setattr(Batch, 'export_excel', corrupt_metadata)
    observed = reference.observe(one_summary_case(), tmp_path)
    assert observed['inputs_unchanged']
    assert any('sheet 0: cells' in value for value in observed['disagreements'])
