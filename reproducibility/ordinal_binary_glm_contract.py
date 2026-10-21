"""Native R scientific controls for unpenalized varying-feature binary fits."""
import ast
import hashlib
import json
from pathlib import Path

ARCHIVE = Path(__file__).with_name('reference-sources') / 'ordinal-binary-glm'
MANIFEST_SHA256 = '0d53a63b6d3cdaf76f174dc3a52d2d5465db07f2cb8bdcb89e625d30d9394ffd'
BEFORE = 'ordinal-binary-glm-before-20261007-v2'
CAPABILITY_PREFIXES = {
    'PyFLASH.modelling._PyFLASHOrdinalLogistic.' + name: ('ordinal-binary-glm.',)
    for name in ('fit', 'predict', 'predict_proba')
}
COMPLETE_CAPABILITIES = frozenset()

CACHE_CARRIER_SHA256 = 'defc8cb62e38758cf7b72153f0eeb9bde293d876cf9288960057282b17e5294a'


def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    verify_manifest(ARCHIVE, 'source-manifest.json', MANIFEST_SHA256, cache_carrier_sha256=CACHE_CARRIER_SHA256)


def cases():
    return json.loads((ARCHIVE / BEFORE / 'frozen-before.json').read_text(encoding='utf-8'))['rows']

def production(row):
    filename = ARCHIVE / BEFORE / 'freeze_ordinal_binary_glm_v2_20261007.py'
    parsed = ast.parse(filename.read_text(encoding='utf-8'))
    function = next(node for node in parsed.body if isinstance(node, ast.FunctionDef) and node.name == 'production')
    namespace = {'CONFIG': {'alpha': 0., 'max_iter': 10000}}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(filename), 'exec'), namespace)
    inputs = json.loads((ARCHIVE / BEFORE / 'original-inputs.json').read_text(encoding='utf-8'))
    case = next(case for case in inputs if case['key'] == row['case_key'])
    return namespace['production'](case, row['first_label'], row['container'])

def agrees(row, actual):
    from reproducibility.ordinal_response_adapter import equal
    return equal(actual, row['expected'])

def validate(output):
    from PyFLASH._persistence import write_json
    from reproducibility.normality_association_validation import comparison
    from reproducibility.reference_runtime import execute_queries, values
    from reproducibility.ordinal_response_adapter import equal
    check_identity()
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    record = json.loads((ARCHIVE / BEFORE / 'frozen-before.json').read_text(encoding='utf-8'))
    queries = json.loads((ARCHIVE / BEFORE / 'native/binomial-glm-queries.json').read_text(encoding='utf-8'))
    original = json.loads((ARCHIVE / BEFORE / 'native/binomial-glm-results.json').read_text(encoding='utf-8'))
    native = execute_queries(queries, output / 'native', name='binomial-glm', timeout=300)
    if any(native[key] != record['native_runtime'][key] for key in ('R', 'webR', 'wasm_sha256')):
        raise ValueError('Native binary fit reference identity changed.')
    old_answers = {row['key']: values(row) for row in original['rows']}
    answers = {row['key']: values(row) for row in native['rows']}
    unchanged = {key: equal(answer, old_answers[key]) for key, answer in answers.items()}
    scope = ('Native R binomial GLM fits the equivalent one-threshold unpenalized '
             'likelihood on nonseparable varying-feature inputs. Compare all fitted '
             'coefficients, thresholds, classes and train/held-out predictions and '
             'probability arrays through the actual wrapper. Positive penalties, '
             'more classes and model search remain outside this conditional family.')
    rows, paired = [], []
    for row in cases():
        actual = production(row)
        reference_unchanged = unchanged[row['case_key']]
        equal_result = reference_unchanged and agrees(row, actual)
        rows.append(comparison(row['key'], 'Native R stats::glm binomial logistic fitting',
                               'ordinal-binary-glm', actual, row['expected'], equal_result,
                               reference_unchanged, scope, 1e-9, 0))
        paired.append({'key': row['key'], 'actual': actual, 'expected': row['expected'],
                       'agrees': equal_result, 'reference_unchanged': reference_unchanged})
        write_json(output / 'ordinal-binary-glm-paired.json', {
            'manifest_sha256': MANIFEST_SHA256, 'scope': scope, 'rows': paired})
    return rows
