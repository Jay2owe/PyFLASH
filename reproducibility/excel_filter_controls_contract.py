"""Frozen workbook/filter representations and pre-write/error controls."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from reproducibility import compact_evidence as storage
from reproducibility import excel_coupled_contract as client

ARCHIVE = Path(__file__).with_name('reference-sources') / 'excel-filter-controls/v1'
MANIFEST_SHA256 = 'eafa2f455455c5e503beb314a6dac6e9d11c5459acd9b79df7070816e7383d28'
COMPLETE_CAPABILITIES = frozenset()
METHODS = ('export_excel', 'export_all_excel', 'export_IF_summary_excel',
           'export_unregistered_summary_excel', 'export_extra_summary_excel',
           'export_behavior_summary_excel', 'export_extended_data_excel')
CAPABILITY_PREFIXES = {'PyFLASH.batch.Batch.' + method: ('excel-filter-controls.' + method + '.',)
                       for method in METHODS}


def declaration():
    from reproducibility.evidence_identity import verify_manifest
    verify_manifest(ARCHIVE, 'source-manifest.json', MANIFEST_SHA256)
    return json.loads((ARCHIVE / 'declaration.json').read_text())


def cases():
    return declaration()['rows']


def required_keys(capability):
    return {row['key'] for row in cases() if row['method'] == capability.rsplit('.', 1)[-1]}


def inputs():
    import ijson
    definition = declaration()
    path = Path(__file__).resolve().parents[1] / definition['canonical_input']['path'].replace('\\', '/')
    expected = definition['canonical_input']
    storage.validate(path, expected)
    wanted = {row['base_input_key'] for row in definition['rows'] if 'base_input_key' in row}
    result = {}
    with path.open('rb') as stream:
        for row in ijson.items(stream, 'rows.item', use_float=True):
            storage.memory_guard()
            if row['key'] in wanted:
                result[row['key']] = row
            if set(result) == wanted:
                break
    assert set(result) == wanted
    return result


def represented(values, container):
    if container == 'tuple': return tuple(values)
    if container == 'set': return set(values)
    if container == 'array':
        import numpy as np
        return np.asarray(values, dtype=object)
    if container == 'series':
        import pandas as pd
        return pd.Series(values, dtype=object)
    if container == 'index':
        import pandas as pd
        return pd.Index(values)
    if container == 'string': return '|'.join('(?:' + value + ')' for value in values)
    if container == 'padded': return [None, '', *['  ' + value + '  ' for value in values], None]
    if container == 'none': return None
    raise ValueError('Undeclared filter representation')


def report_block(include, exclude):
    lines = lambda values: '\n'.join('- ' + value for value in values) if values else '- none'
    return 'Include regex:\n' + lines(include) + '\n\nExclude regex:\n' + lines(exclude) + '\n'


def observe(case, output, declared_inputs):
    from PyFLASH.batch import Batch
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if case['kind'] == 'representation':
        row = deepcopy(declared_inputs[case['base_input_key']])
        original_options = deepcopy(row['options'])
        runtime = deepcopy(row['options'])
        for name, normalized in case['expected_patterns'].items():
            runtime[name] = represented(original_options[name], case['container'])
            row['options'][name] = normalized
        for workbook in row['expected_workbooks']:
            prefix = workbook['request']['kind'] + '_' if case['method'] in METHODS[:2] else ''
            inc, exc = prefix + 'include', prefix + 'exclude'
            old = report_block(original_options[inc], original_options[exc])
            new = report_block(row['options'][inc], row['options'][exc])
            assert old in workbook['regex_report']
            workbook['regex_report'] = workbook['regex_report'].replace(old, new, 1)
        row['key'] = case['key']
        row['_case_digest'] = hashlib.sha256(json.dumps(row, sort_keys=True, allow_nan=False).encode()).hexdigest()
        actual = client.observe(row, output, call_options=runtime)
        assert not actual['disagreements'], actual['disagreements']
        return actual
    if case['kind'] == 'invalid-parent':
        batch = client.literal_batch(output, declared_inputs[case['base_input_key']])
        options = {case['parameter']: {'string': '[', 'list': ['['], 'tuple': ('[',)}[case['container']]}
        try:
            getattr(batch, case['method'])(save_path=output / 'exports', **options)
        except ValueError as error:
            assert str(error).startswith('Invalid ' + case['parameter'].rsplit('_', 1)[-1] + ' regex')
        else:
            raise AssertionError('Invalid parent filter was accepted')
        partial = [str(path.relative_to(output)) for path in output.rglob('*')
                   if path.is_file() and (path.suffix == '.xlsx' or path.name.endswith('_RegexFilters.txt'))]
        assert not partial, 'Invalid parent filter left partial outputs: ' + str(partial)
        return dict(expected_refusal=True, no_partial_outputs=True)
    failure = case['failure']
    error = KeyError('declared data mapping failure') if failure == 'lookup-key' else AttributeError('declared data read failure')
    class BrokenData(Batch):
        @property
        def data(self): raise error
    class BrokenMapping:
        def __getitem__(self, key): raise error
    batch = object.__new__(BrokenData if failure == 'data-descriptor' else Batch)
    if failure.startswith('lookup-'): batch.data = BrokenMapping()
    elif failure == 'no-key': batch.data = {}
    elif failure == 'no-df': batch.data = {'Behaviour': object()}
    options = dict(if_summary=False, if_extended=False, unregistered_summary=False) if case['method'] in METHODS[:2] else {}
    caught, result = None, None
    try:
        result = getattr(batch, case['method'])(save_path=output / 'exports', **options)
    except Exception as exc:
        caught = exc
    if case['expected_error']:
        assert caught is error, 'Genuine data read failure was hidden or replaced'
    else:
        assert caught is None
        assert result == ([] if case['method'] in METHODS[:2] else None)
    assert not [path for path in output.rglob('*') if path.is_file()]
    return dict(original_error_preserved=bool(case['expected_error']), no_partial_outputs=True)


def validate(output):
    import traceback
    from PyFLASH._persistence import write_json
    from reproducibility.normality_association_validation import comparison
    declared = inputs()
    rows, paired = [], []
    for index, case in enumerate(cases()):
        actual, error = None, None
        try:
            actual = observe(case, Path(output) / f'filter-{index:03d}', declared)
        except Exception:
            error = traceback.format_exc()
        agrees = error is None
        rows.append(comparison(case['key'], 'frozen-literal-workbooks/native-openpyxl',
            'functional-export-controls/no-estimator-vote', {'complete_match': agrees},
            {'complete_match': True}, agrees, True, 'exact-cells-reports-paths-and-error-ownership', 0, 0))
        paired.append(dict(case=case, observed=actual, error=error, agrees=agrees))
    write_json(Path(output) / 'excel-filter-controls-paired.json', dict(complete_contract=False, rows=paired))
    return rows
