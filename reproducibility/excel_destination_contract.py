"""Direct exporter destinations preserve predeclared complete workbook answers.

The authenticated coupled client supplies expected cells and reports. Only the
declared destination and workbook name change; candidate output is never used
to construct expected values. This is supporting coverage, not whole-contract
qualification.
"""
from copy import deepcopy
from pathlib import Path

import pandas as pd

from reproducibility import excel_coupled_contract as client
from reproducibility import excel_workbook_schema_contract as schema


METHODS = (
    'export_IF_summary_excel', 'export_unregistered_summary_excel',
    'export_extra_summary_excel', 'export_behavior_summary_excel',
    'export_extended_data_excel',
)


def declared_rows():
    import hashlib
    import ijson
    import json
    from reproducibility.evidence_identity import verify_manifest
    verify_manifest(client.ARCHIVE, 'source-manifest.json', client.MANIFEST_SHA256)
    selected = {}
    with (client.ARCHIVE / 'client-reference.json').open('rb') as stream:
        for row in ijson.items(stream, 'rows.item', use_float=True):
            method = row['method']
            if method in METHODS and method not in selected:
                row['_case_digest'] = hashlib.sha256(json.dumps(
                    row, sort_keys=True, allow_nan=False).encode('utf-8')).hexdigest()
                selected[method] = row
            if len(selected) == len(METHODS):
                break
    if set(selected) != set(METHODS):
        raise ValueError('Frozen client is missing a required direct exporter')
    return selected


COMPLETE_CAPABILITIES = frozenset()
CAPABILITY_PREFIXES = {'PyFLASH.batch.Batch.' + method: ('excel-destination.' + method + '.',)
                       for method in METHODS}


def cases():
    successful = [dict(method=method, destination=destination, name=name,
                 key=f'excel-destination.{method}.{destination}.name-{index}')
            for method in METHODS
            for destination in ('default', 'absolute', 'relative', 'generated')
            for index, name in enumerate((None, 'Selected', 'Selected.XLSX', ' Selected.xlsx ', '', '   '))]
    refused = [dict(method=method, target=target, container=container,
                    key=f'excel-destination.{method}.invalid-{target}.{container}')
               for method in METHODS for target in ('include', 'exclude')
               for container in ('string', 'list', 'tuple')]
    return successful + refused


def required_keys(capability):
    return {row['key'] for row in cases() if row['method'] == capability.rsplit('.', 1)[-1]}


def observe(
        tmp_path, declared_rows, method, destination, name):
    row = declared_rows[method]
    batch = client.literal_batch(tmp_path, row)
    frames = [*batch.summaries.values(), batch.data['Behaviour'].df,
              *[exp.summary for exp in batch.experiment_list],
              *[obj.df for exp in batch.experiment_list for obj in exp.data.values()]]
    originals = [frame.copy(deep=True) for frame in frames]
    attributes = [deepcopy(frame.attrs) for frame in frames]
    groups = client.group_state(batch.condition_list.condition_list)
    macros = {p.relative_to(tmp_path): p.read_bytes()
              for p in tmp_path.glob('source-*/**/*.txt')}
    options = deepcopy(row['options'])
    if name is not None:
        options['save_name'] = name
    if destination == 'generated':
        del batch.export_path
        expected_directory = Path(batch.filePath) / 'Exports'
    elif destination == 'relative':
        options['save_path'] = 'nested/exports'
        expected_directory = Path(batch.export_path) / 'nested/exports'
    elif destination == 'absolute':
        options['save_path'] = tmp_path / 'absolute destination'
        expected_directory = options['save_path']
    else:
        expected_directory = Path(batch.export_path)
    expected = row['expected_workbooks']
    assert len(expected) == 1
    book = expected[0]
    basename = book['request']['name'] if name in (None, '', '   ') else 'Selected'
    expected_paths = [expected_directory / (basename + ending)
                      for ending in ('.xlsx', '_RegexFilters.txt')]
    outputs = getattr(batch, method)(**options)
    assert [Path(path).resolve() for path in outputs] == [p.resolve() for p in expected_paths]
    worksheets = schema.read_workbook(expected_paths[0])
    assert [dict(name=s['name'], cells=s['cells'], merged_ranges=s['merged_ranges'])
            for s in worksheets] == book['worksheets']
    assert not any(s['formula_cells'] for s in worksheets)
    report = book['regex_report'].replace(
        'Workbook: ' + book['request']['name'] + '.xlsx',
        'Workbook: ' + basename + '.xlsx')
    assert expected_paths[1].read_text(encoding='utf-8') == report
    assert sorted(p.resolve() for p in expected_directory.iterdir()) == sorted(
        p.resolve() for p in expected_paths)
    for actual, original, attrs in zip(frames, originals, attributes):
        pd.testing.assert_frame_equal(actual, original, check_exact=True)
        assert actual.attrs == attrs
    assert client.group_state(batch.condition_list.condition_list) == groups
    assert {p.relative_to(tmp_path): p.read_bytes()
            for p in tmp_path.glob('source-*/**/*.txt')} == macros
    return dict(outputs=[str(p.resolve()) for p in expected_paths],
                complete_cells_reports_and_inputs_match=True)


def observe_case(folder, declared, case):
    if 'target' not in case:
        return observe(folder, declared, case['method'], case['destination'], case['name'])
    batch = client.literal_batch(folder, declared[case['method']])
    frames = [*batch.summaries.values(), batch.data['Behaviour'].df,
              *[exp.summary for exp in batch.experiment_list],
              *[obj.df for exp in batch.experiment_list for obj in exp.data.values()]]
    originals = [frame.copy(deep=True) for frame in frames]
    attrs = [deepcopy(frame.attrs) for frame in frames]
    before = {p.relative_to(folder): p.read_bytes() for p in folder.rglob('*') if p.is_file()}
    options = deepcopy(declared[case['method']]['options'])
    options[case['target']] = {'string': '[', 'list': ['['], 'tuple': ('[',)}[case['container']]
    try:
        getattr(batch, case['method'])(**options)
    except ValueError as exc:
        assert str(exc).startswith('Invalid ' + case['target'] + ' regex')
    else:
        raise AssertionError('Malformed regex was accepted')
    assert {p.relative_to(folder): p.read_bytes() for p in folder.rglob('*') if p.is_file()} == before
    for actual, original, original_attrs in zip(frames, originals, attrs):
        pd.testing.assert_frame_equal(actual, original, check_exact=True)
        assert actual.attrs == original_attrs
    return dict(expected_refusal=True, no_partial_files=True, inputs_unchanged=True)


def validate(output):
    import traceback
    from PyFLASH._persistence import write_json
    from reproducibility.normality_association_validation import comparison
    declared = declared_rows()
    client.check_parameter_inventory()
    rows, paired = [], []
    for index, case in enumerate(cases()):
        folder = Path(output) / f'case-{index:03d}'
        folder.mkdir(parents=True, exist_ok=False)
        result, error = None, None
        try:
            result = observe_case(folder, declared, case)
        except Exception:
            error = traceback.format_exc()
        agrees = error is None
        rows.append(comparison(case['key'], 'predeclared-coupled-client/native-openpyxl-reader',
            'functional-direct-workbook-destination/no-extra-estimator-vote',
            {'complete_output_matches': agrees}, {'complete_output_matches': True}, agrees, True,
            'exact-cells-sheets-merged-ranges-formula-absence-reports-paths-and-input-ownership', 0., 0.))
        paired.append(dict(case=case, observed=result, error=error, agrees=agrees))
    write_json(Path(output) / 'excel-destination-paired.json', dict(
        schema_version=1, complete_contract=False, rows=paired))
    return rows
