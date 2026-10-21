"""Accepted native distribution coordinates plus literal queue/count boundaries."""
from pathlib import Path
import ast
import hashlib
import json

ARCHIVE = Path(__file__).with_name('reference-sources') / 'ecdf-public'
MANIFEST_SHA256 = '09d641e290e06fc8a1d58b90979d15668952cdbf4d8c90752bc87dd08e7eb343'
CAPABILITY_PREFIXES = {'ecdf': ('ecdf-public.',)}
COMPLETE_CAPABILITIES = frozenset()


def read(owner, name):
    return json.loads((ARCHIVE / owner / name).read_text(encoding='utf-8'))


CACHE_CARRIER_SHA256 = '2f62ac7a14ad721cee922449dc15e0530e929efb73905522317c9d3aa6c8bf65'


def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    verify_manifest(ARCHIVE, 'source-manifest.json', MANIFEST_SHA256, cache_carrier_sha256=CACHE_CARRIER_SHA256)



def cases():
    finite = {row['case']['key']: row for row in read('ecdf-finite-display-native-qualified-20261007-v1', 'run.json')['rows']}
    rows = read('ecdf-public-native-before-20261007-v1', 'cases.json')
    for row in rows:
        if row['reference']['case']['key'] == 'nonfinite':
            row['reference'] = finite['nonfinite']
    for stat in ('proportion', 'count'):
        for complementary in (False, True):
            rows.append({'key': 'all-infinite.' + stat + ('.complementary' if complementary else '.ordinary'), 'stat': stat, 'complementary': complementary, 'reference': finite['all-infinite']})
    cases = [{'key': 'ecdf-public.native.' + row['key'], 'kind': 'native', 'case': row} for row in rows]
    cases += [{'key': 'ecdf-public.labels.' + row['case']['key'], 'kind': 'labels', 'case': row['case'], 'original': row['result']} for row in read('ecdf-queue-label-before-20261007-v2', 'frozen-before.json')['rows']]
    return cases


def required_keys(capability):
    return {row['key'] for row in cases()} if capability == 'ecdf' else set()


def _functions(owner, filename, names):
    import numpy as np
    import pandas as pd
    from PyFLASH import from_dataframe, ConditionBuilder
    from PyFLASH import plotting as P
    from types import SimpleNamespace
    path = ARCHIVE / owner / filename
    tree = ast.parse(path.read_text(encoding='utf-8'))
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    namespace = dict(globals(), np=np, pd=pd, P=P, from_dataframe=from_dataframe, ConditionBuilder=ConditionBuilder, SimpleNamespace=SimpleNamespace)
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


def check_native_references(output):
    """Execute the original accepted R expressions; reject changed native answers."""
    from reproducibility.reference_runtime import execute_queries
    output = Path(output)
    for owner, stem in [('ecdf-native-original-inputs-20261007-v1', 'ecdf-native'), ('ecdf-finite-display-native-qualified-20261007-v1', 'finite-display-ecdf')]:
        original = read(owner, 'native-r/' + stem + '-results.json')
        queries = read(owner, 'native-r/' + stem + '-queries.json')
        current = execute_queries(queries, output / owner, name=stem, timeout=180)
        for field in ('R', 'webR', 'wasm_sha256'):
            if current[field] != original[field]:
                raise ValueError('Accepted native ECDF runtime changed: ' + field)
        if current['rows'] != original['rows']:
            raise ValueError('Accepted native ECDF answers changed.')


def check_result(item, actual):
    if item['kind'] == 'labels':
        assert actual['records'] and all(row['xlabel'] == item['case']['label'] for row in actual['records'])
        assert not actual['saved_figures']
        assert len(actual['records']) == len(item['original']['records'])
        for a, b in zip(actual['records'], item['original']['records']):
            assert {key: value for key, value in a.items() if key != 'xlabel'} == {key: value for key, value in b.items() if key != 'xlabel'}
        return 'Literal queue/label contract; all original scientific curves unchanged.'
    namespace = _functions('ecdf-public-native-before-20261007-v1', 'compare_public_ecdf_native_20261007.py', {'decode', 'score'})
    scope = namespace['score'](item['case'], actual)
    case = item['case']
    n = case['reference']['native_r']['n']
    if not n:
        assert not actual['returned'].get('n') or actual['returned']['n'] == [0]
        return scope
    # All returned count/unit fields belong to the scientific contract too.
    assert actual['returned'] == {'group': ['Control'], 'n': [n]}
    plot = actual['records'][0]
    assert plot['xlabel'] == 'A Volume (µm³)'
    expected_label = 'Count' if case['stat'] == 'count' else 'Proportion'
    if case['complementary']: expected_label = 'Complementary ' + expected_label
    assert plot['ylabel'] == expected_label and plot['title'] == '' and plot['texts'] == []
    external = case['reference']['native_scipy']
    if external['status'] == 'executed':
        import numpy as np
        line = plot['lines'][0]
        x, y = namespace['decode'](line['x']), namespace['decode'](line['y'])
        knots = namespace['decode'](external['knots'])
        expected = external['survival'] if case['complementary'] else external['proportions']
        if case['stat'] == 'count': expected = np.asarray(expected) * n
        actual_knots = [y[max(i for i, value in enumerate(x) if value == knot)] for knot in knots]
        np.testing.assert_allclose(actual_knots, expected, rtol=1e-12, atol=0)
    return scope


def production(item, output):
    output = Path(output)
    if item['kind'] == 'labels':
        namespace = _functions('ecdf-queue-label-before-20261007-v2', 'freeze_ecdf_queue_labels_v2_20261007.py', {'production'})
    else:
        namespace = _functions('ecdf-public-native-before-20261007-v1', 'compare_public_ecdf_native_20261007.py', {'decode', 'encode', 'production'})
    actual = namespace['production'](item['case'], output / item['key'])
    scope = check_result(item, actual)
    return actual, scope


def validate(output):
    from PyFLASH._persistence import write_json
    from reproducibility.normality_association_validation import comparison
    check_identity()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    check_native_references(output / 'native-r')
    rows, paired = [], []
    for item in cases():
        try:
            actual, scope = production(item, output)
            agree = True
        except Exception as exc:
            actual, scope, agree = {'error_type': type(exc).__name__, 'error': str(exc)}, 'Failed public ECDF control', False
        reference = 'Literal queue/label compatibility' if item['kind'] == 'labels' else 'Native R stats::ecdf/rank + frozen SciPy stats.ecdf'
        rows.append(comparison(item['key'], reference, 'ecdf-scientific-and-functional', actual, item, agree, True, scope, 1e-12 if item['kind'] == 'native' else 0, 0))
        paired.append({'item': item, 'actual': actual, 'agrees': agree, 'scope': scope})
    write_json(output / 'ecdf-public-paired.json', {'rows': paired, 'scope': 'Native full scientific step arrays on explicit finite display admission; original raw infinity/default differences remain preserved. Selection, other options and final whole-plot rendering remain open.'})
    return rows
