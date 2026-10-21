"""Functional outlier request/metadata controls; statistical parent coverage stays open."""
import ast
import hashlib
import json
from pathlib import Path

ARCHIVE = Path(__file__).with_name('reference-sources') / 'outlier-requests'
MANIFEST_SHA256 = 'd0725670cc6e51efd124ce8e234c2fa42073314fa5946c255bc8dd31cc220133'
BEFORE = 'outlier-requests-before-20261007-v1'
QUALIFIED = 'outlier-requests-qualified-20261007-v1'
CAPABILITY_PREFIXES = {
    'PyFLASH.exclusions.mark_outliers': ('outlier-request.mark_outliers.',),
    'PyFLASH.exclusions.exclude_outliers': ('outlier-request.exclude_outliers.',),
    'PyFLASH.pipeline.data_overview': ('outlier-request.data_overview.',),
}
COMPLETE_CAPABILITIES = frozenset()

CACHE_CARRIER_SHA256 = 'dbe2622e754f2d9da559a547b6e3c01ce433e0db69397f8d4cd51a62b6eea262'


def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    verify_manifest(ARCHIVE, 'source-manifest.json', MANIFEST_SHA256, cache_carrier_sha256=CACHE_CARRIER_SHA256)


def cases():
    return json.loads((ARCHIVE / BEFORE / 'frozen-before.json').read_text(encoding='utf-8'))['rows']

def expected_tables():
    rows = json.loads((ARCHIVE / QUALIFIED / 'complete-table-compatibility.json').read_text(encoding='utf-8'))['rows']
    return {row['key']: row['expected_tables'] for row in rows}

def production(row, output):
    from types import SimpleNamespace
    filename = ARCHIVE / BEFORE / 'freeze_outlier_requests_20261007.py'
    parsed = ast.parse(filename.read_text(encoding='utf-8'))
    functions = [node for node in parsed.body if isinstance(node, ast.FunctionDef)
                 and node.name in ('method_value', 'production')]
    namespace = {'Path': Path, 'SimpleNamespace': SimpleNamespace, 'json': json,
                 'CONFIG': {'values': [1., 2., 3., 4., 5., 100.]}}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(filename), 'exec'), namespace)
    return namespace['production'](row, Path(output) / row['key'])

def agrees(row, actual):
    if row['expected_error']:
        return actual['error_type'] == row['expected_error'] and actual['inputs_unchanged']
    return (actual['error_type'] is None and actual['inputs_unchanged']
            and actual['actual_methods'] == row['expected_methods']
            and actual['actual_flags'] == row['expected_flags']
            and actual['tables'] == expected_tables()[row['key']])

def validate(output):
    from PyFLASH._persistence import write_json
    from reproducibility.normality_association_validation import comparison
    check_identity()
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    rows, paired = [], []
    scope = ('Literal method representation/consumption, scope refusal and unchanged '
             'complete returned tables compared with original healthy controls. '
             'Functional request/compatibility boundary, no scientific detector vote '
             'or whole outlier/overview parent certificate.')
    for row in cases():
        actual = production(row, output)
        equal = agrees(row, actual)
        expected = {'methods': row['expected_methods'], 'flags': row['expected_flags'],
                    'error_type': row['expected_error'], 'tables': expected_tables().get(row['key'])}
        rows.append(comparison(row['key'], 'Literal request contract and original healthy-table compatibility',
                               'outlier-request', actual, expected, equal, True, scope, 0, 0))
        paired.append({'key': row['key'], 'actual': actual, 'expected': expected, 'agrees': equal})
        write_json(output / 'outlier-request-paired.json', {
            'manifest_sha256': MANIFEST_SHA256, 'scope': scope, 'rows': paired})
    return rows
