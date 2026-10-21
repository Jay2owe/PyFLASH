"""Literal native workbook outputs across real summary-cache lifecycle states."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from reproducibility import compact_evidence as storage
from reproducibility import excel_coupled_contract as client

ARCHIVE = Path(__file__).with_name('reference-sources') / 'excel-summary-lifecycle/v1'
MANIFEST_SHA256 = '2f6182d7f790fa9f05cf3f9c85d65ad000ad2f34d3536299f616c44667b1d04c'
COMPLETE_CAPABILITIES = frozenset()
CAPABILITY_PREFIXES = {cap: ('excel-summary-lifecycle.' + cap.rsplit('.', 1)[-1] + '.',)
                       for cap in client.CAPABILITY_PREFIXES}


def declaration():
    from reproducibility.evidence_identity import verify_manifest
    verify_manifest(ARCHIVE, 'source-manifest.json', MANIFEST_SHA256)
    return json.loads((ARCHIVE / 'declaration.json').read_text())


def cases(): return declaration()['rows']


def required_keys(capability):
    return {row['key'] for row in cases() if row['method'] == capability.rsplit('.', 1)[-1]}


def inputs():
    import ijson
    d = declaration()
    path = Path(__file__).resolve().parents[1] / d['canonical_input']['path']
    storage.validate(path, d['canonical_input'])
    wanted = {row['base_input_key'] for row in d['rows'] if 'base_input_key' in row}
    result = {}
    with path.open('rb') as stream:
        for row in ijson.items(stream, 'rows.item', use_float=True):
            storage.memory_guard()
            if row['key'] in wanted: result[row['key']] = row
            if set(result) == wanted: break
    assert set(result) == wanted
    return result


def reference_case(case, declared):
    row = deepcopy(declared[case['base_input_key']])
    row['key'] = case['key']
    if case.get('rebuilt_regions') is not None and case['method'] in ('export_excel', 'export_all_excel'):
        books = row['expected_workbooks']
        row['expected_workbooks'] = [book for region in case['rebuilt_regions'] for book in books
                                    if book['request']['region'] == region] + [
                                        book for book in books if book['request']['region'] is None]
    if case.get('header_only_summary_tables'):
        groups = row['design']['group_names']
        for book in row['expected_workbooks']:
            if book['request']['kind'] not in ('if_summary', 'unregistered_summary'): continue
            for sheet in book['worksheets']:
                if sheet['cells'] and sheet['cells'][0] == groups:
                    if sheet['merged_ranges']:
                        # The accepted native tables place descriptions after
                        # one spacer row. Remove values, retaining annotations.
                        import re
                        starts = [int(re.search(r'\d+', area).group()) for area in sheet['merged_ranges']]
                        removed = min(starts) - 3
                        assert removed >= 0
                        sheet['cells'] = sheet['cells'][:1] + sheet['cells'][removed + 1:]
                        sheet['merged_ranges'] = [re.sub(r'\d+', lambda match: str(int(match.group()) - removed), area)
                                                  for area in sheet['merged_ranges']]
                    else:
                        sheet['cells'] = sheet['cells'][:1]
    row['_case_digest'] = hashlib.sha256(json.dumps(row, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return row


def observe(case, output, declared):
    import pandas as pd
    from PyFLASH.batch import Batch
    from types import SimpleNamespace
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    calls, owners = [], []
    if case['kind'] == 'error':
        error_type = {'TypeError': TypeError, 'OSError': OSError, 'KeyboardInterrupt': KeyboardInterrupt}[case['error_type']]
        error = error_type('declared lifecycle callback failure')
        def modern(*, progress):
            calls.append(progress)
            raise error
        def old():
            calls.append('legacy')
            raise error
        batch = object.__new__(Batch)
        batch.name = 'literal lifecycle error'
        batch.summaries = {}
        batch.experiment_list = [SimpleNamespace(summaries={}, summary=None,
            createSummary=old if case['legacy'] else modern)]
        caught = None
        try: getattr(batch, case['method'])(save_path=output / 'exports')
        except BaseException as exc: caught = exc
        assert caught is error, 'Callback error object replaced or hidden'
        assert calls == (['legacy'] if case['legacy'] else [False]), 'Callback repeated or wrong arguments'
        assert not [p for p in output.rglob('*') if p.is_file()]
        return dict(original_error_preserved=True, calls=calls, no_partial_outputs=True)
    row = reference_case(case, declared)
    def setup(batch, reference):
        owners.append(batch)
        assert len(batch.experiment_list) == 1
        exp = batch.experiment_list[0]
        supplied = {region: client.frame(packet) for region, packet in reference['design']['summaries'].items()}
        def modern(*, progress):
            calls.append(progress)
            exp.summaries = {region: frame.copy(deep=True) for region, frame in supplied.items()}
            exp.summary = exp.summaries['SCN']
        def old():
            calls.append('legacy')
            exp.summaries = {region: frame.copy(deep=True) for region, frame in supplied.items()}
            exp.summary = exp.summaries['SCN']
        exp.createSummary = old if case.get('legacy') or case.get('state') == 'legacy-callback' else modern
        if case['kind'] == 'bypass':
            batch.summaries = {}
            exp.summaries = {}
            return
        state = case['state']
        if state == 'provided': return
        if state == 'zero-rows':
            batch.summaries = {region: frame.iloc[:0].copy() for region, frame in batch.summaries.items()}
            return
        batch.summaries = {}
        exp.summaries = {region: frame.copy(deep=True) for region, frame in supplied.items()}
        if state == 'missing-batch': del batch.summaries
        elif state == 'none-batch': batch.summaries = None
        elif state == 'empty-columns': batch.summaries = {'SCN': pd.DataFrame()}
        elif state == 'legacy-batch': batch.__dict__['summary'] = supplied['SCN'].copy(deep=True)
        elif state == 'child-legacy': exp.summaries = {}
        elif state in ('modern-callback', 'legacy-callback'):
            exp.summaries, exp.summary = {}, pd.DataFrame()
    actual = client.observe(row, output, owner_setup=setup)
    assert not actual['disagreements'], actual['disagreements']
    assert len(calls) == case['expected_callback_calls'], 'Unexpected summary callback count'
    if calls: assert calls == (['legacy'] if case.get('state') == 'legacy-callback' else [False])
    if case['kind'] == 'bypass': assert owners[0].summaries == {}, 'Summary cache unexpectedly rebuilt'
    actual['callback_calls'] = calls
    return actual


def validate(output):
    import traceback
    from PyFLASH._persistence import write_json
    from reproducibility.normality_association_validation import comparison
    declared = inputs()
    paired, rows = [], []
    for index, case in enumerate(cases()):
        actual, error = None, None
        try: actual = observe(case, Path(output) / f'lifecycle-{index:03d}', declared)
        except Exception: error = traceback.format_exc()
        agrees = error is None
        rows.append(comparison(case['key'], 'predeclared-literal-client/native-openpyxl',
            'functional-summary-lifecycle/no-estimator-vote', {'complete_match': agrees},
            {'complete_match': True}, agrees, True, 'exact-cells-reports-paths-callbacks-and-exception-identity', 0, 0))
        paired.append(dict(case=case, observed=actual, error=error, agrees=agrees))
    write_json(Path(output) / 'excel-summary-lifecycle-paired.json', dict(complete_contract=False, rows=paired))
    return rows
