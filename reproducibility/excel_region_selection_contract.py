"""Frozen direct region and progress controls, without whole-export approval."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import traceback

from reproducibility import excel_coupled_contract as client
from reproducibility import compact_evidence as storage

ARCHIVE = Path(__file__).with_name('reference-sources') / 'excel-direct-regions/v1'
MANIFEST_SHA256 = 'af7eb88810f2872861c70f755f4370d677870bcec492cbef297a0e8fa7721c08'
COMPLETE_CAPABILITIES = frozenset()
CAPABILITY_PREFIXES = {'PyFLASH.batch.Batch.' + method: ('excel-direct-region.' + method + '.',)
    for method in ('export_IF_summary_excel', 'export_extra_summary_excel',
                   'export_unregistered_summary_excel', 'export_extended_data_excel')}


def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    verify_manifest(ARCHIVE, 'source-manifest.json', MANIFEST_SHA256)
    path = ARCHIVE / 'declaration.json'
    assert path.stat().st_size < 2 * 1024**2
    result = json.loads(path.read_text(encoding='utf-8'))
    assert result['candidate_execution_observed'] is False and result['cases'] == 31
    return result


def cases():
    return check_identity()['rows']


def required_keys(capability):
    return {row['key'] for row in cases() if row['method'] == capability.rsplit('.', 1)[-1]}


def inputs(declaration=None):
    import ijson
    declaration = check_identity() if declaration is None else declaration
    root = Path(__file__).resolve().parents[1]
    expected = declaration['canonical_input']
    fixture = root / expected['path'].replace('\\', '/')
    assert fixture.stat().st_size == expected['size']
    assert storage.digest(fixture, check_resources=True) == expected['sha256']
    wanted = {row['base_input_key'] for row in declaration['rows']}
    result = {}
    with fixture.open('rb') as stream:
        for row in ijson.items(stream, 'rows.item', use_float=True):
            if row['key'] in wanted:
                result[row['key']] = row
            if set(result) == wanted:
                break
    assert set(result) == wanted
    return result


def observe(case, output, declared_inputs):
    row = deepcopy(declared_inputs[case['base_input_key']])
    row.update({key: deepcopy(value) for key, value in case.items() if key != 'base_input_key'})
    row['_case_digest'] = hashlib.sha256(json.dumps(row, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return client.observe(row, output)


def validate(output):
    from PyFLASH._persistence import write_json
    from reproducibility.normality_association_validation import comparison
    declaration = check_identity()
    declared_inputs = inputs(declaration)
    paired, comparisons = [], []
    for case in declaration['rows']:
        actual, error = None, None
        try:
            actual = observe(case, output, declared_inputs)
        except Exception:
            error = traceback.format_exc()
        agrees = error is None and not actual['disagreements']
        comparisons.append(comparison(case['key'], 'predeclared-literal-client/native-openpyxl',
            'functional-region-and-progress-selection/no-extra-estimator-vote',
            {'complete_output_matches': agrees}, {'complete_output_matches': True}, agrees, True,
            'exact-cells-reports-paths-formula-absence-and-unchanged-inputs', 0., 0.))
        paired.append(dict(case=case, observed=actual, error=error, agrees=agrees))
    write_json(Path(output) / 'excel-direct-region-paired.json', dict(
        schema_version=1, complete_contract=False, rows=paired))
    return comparisons
