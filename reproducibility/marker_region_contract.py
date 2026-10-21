"""Actual selected-region curves with unchanged native R and SciPy references."""
from pathlib import Path
import ast
import hashlib
import json

ARCHIVE = Path(__file__).with_name('reference-sources') / 'marker-regions'
MANIFEST_SHA256 = '75121540a5f3011c4941750bf8798ba913da0d1f55a83e177cd7da246684f062'
CAPABILITY_PREFIXES = {'ecdf': ('ecdf-regions.',)}
COMPLETE_CAPABILITIES = frozenset()
ORIGINAL = 'marker-plot-regions-before-20261007-v3'
SCIPY = 'marker-plot-regions-scipy-qualified-20261007-v1'


def read(owner, filename):
    return json.loads((ARCHIVE / owner / filename).read_text(encoding='utf-8'))


CACHE_CARRIER_SHA256 = 'bb8735c3cbe8e18712c1c1def360e84674bf28eeb2ed97c037a085f4b3176332'


def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    verify_manifest(ARCHIVE, 'source-manifest.json', MANIFEST_SHA256, cache_carrier_sha256=CACHE_CARRIER_SHA256)


def cases():
    return [{'key': 'ecdf-regions.' + row['case']['key'], 'case': row['case']}
            for row in read(ORIGINAL, 'frozen-before.json')['rows']]


def native_rows():
    rows = {}
    for row in read(ORIGINAL, 'native-r/marker-region-distributions-results.json')['rows']:
        values = row['values']
        n, k = int(values[0]), int(values[1])
        rows[row['key']] = ({'n': 0, 'undefined': bool(values[2])} if not n else
            {'n': n, 'knots': values[2:2+k], 'proportions': values[2+k:2+2*k],
             'sorted': values[2+2*k:2+2*k+n], 'ranks': values[2+2*k+n:]})
    return rows


def functions():
    from types import SimpleNamespace
    import numpy as np
    import pandas as pd
    from PyFLASH import from_dataframe, ConditionBuilder, plotting as P
    path = ARCHIVE / ORIGINAL / 'freeze_marker_plot_regions_v3_20261007.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('production', 'encode', 'score')]
    namespace = dict(np=np, pd=pd, from_dataframe=from_dataframe, ConditionBuilder=ConditionBuilder,
                     SimpleNamespace=SimpleNamespace, P=P, native_rows=native_rows(),
                     objects=read(ORIGINAL, 'original-objects.json'))
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


def check_native_references(output):
    from reproducibility.reference_runtime import execute_queries
    stem = 'marker-region-distributions'
    original = read(ORIGINAL, 'native-r/' + stem + '-results.json')
    queries = read(ORIGINAL, 'native-r/' + stem + '-queries.json')
    actual = execute_queries(queries, output, name=stem, timeout=180)
    for field in ('R', 'webR', 'wasm_sha256', 'rows'):
        if actual[field] != original[field]:
            raise ValueError('Accepted native marker-region reference changed: ' + field)


def check_result(item, actual):
    import numpy as np
    case = item['case']
    functions()['score'](case, actual)
    scipy = read(SCIPY, 'native-scipy-original-selected-inputs.json')
    by_roi = {}
    for expected, record in zip(case['expected'], actual['records']):
        group = by_roi.setdefault(expected['roi'], {'group': [], 'n': []})
        group['group'].append(expected['condition'] or expected['factor_value'])
        group['n'].append(len(expected['values']))
        if not expected['values']:
            continue
        assert record['xlabel'] == 'A Volume (µm³)'
        label = 'Count' if case['stat'] == 'count' else 'Proportion'
        if case['complementary']: label = 'Complementary ' + label
        assert record['ylabel'] == label and record['texts'] == [] and record['axis_on']
        reference = scipy[expected['native_key']]
        assert reference['original_values'] == expected['values']
        line = record['lines'][0]
        values = [line['y'][max(i for i, value in enumerate(line['x']) if value == knot)]
                  for knot in reference['quantiles']]
        targets = reference['survival'] if case['complementary'] else reference['cdf']
        if case['stat'] == 'count': targets = np.asarray(targets) * len(expected['values'])
        np.testing.assert_allclose(values, targets, rtol=1e-12, atol=0)
    expected_return = by_roi if case['roi'] is None or isinstance(case['roi'], list) else by_roi[case['roi']]
    assert actual['returned'] == expected_return
    assert actual['caller_tables_unchanged']
    return 'Native full selected-region scientific curves, original group/count fields and empty display domains.'


def production(item, output):
    actual = functions()['production'](item['case'], Path(output) / item['key'])
    return actual, check_result(item, actual)


def validate(output):
    from PyFLASH._persistence import write_json
    from reproducibility.normality_association_validation import comparison
    output = Path(output);output.mkdir(parents=True, exist_ok=True)
    check_identity();check_native_references(output / 'native-r')
    rows, paired = [], []
    for item in cases():
        try:
            actual, scope = production(item, output)
            agree = True
        except Exception as exc:
            actual, scope, agree = {'error_type': type(exc).__name__, 'error': str(exc)}, 'Failed marker-region scientific/control case', False
        rows.append(comparison(item['key'], 'Native R stats.ecdf/rank + frozen native SciPy stats.ecdf + SQL original row membership',
                               'selected-region-scientific-and-functional', actual, item, agree, True, scope, 1e-12, 0))
        paired.append({'item': item, 'actual': actual, 'agree': agree, 'scope': scope})
    write_json(output / 'marker-region-paired.json', {'rows': paired,
        'scope': 'All scientific steps and native unique knots on these selected-region/group requests. Other whole-plot options, sibling complete methods and final rendering remain open.'})
    return rows
