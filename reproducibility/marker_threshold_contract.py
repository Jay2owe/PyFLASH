"""Literal controls for marker thresholds through real constructor/import consumers."""
from pathlib import Path
import ast
import hashlib
import json

ARCHIVE = Path(__file__).with_name('reference-sources') / 'marker-threshold'
MANIFEST_SHA256 = '7a85db15fe905092c757af3f0bcffb3d694e85a86c3d3b18dbeb989a3455e43c'
SOURCES = (
    ('constructor', 'marker-threshold-before-20261007-v2', 'freeze_marker_threshold_v2_20261007.py', 'execute'),
    ('nearest', 'marker-nearest-threshold-before-20261007-v1', 'freeze_marker_nearest_threshold_20261007.py', 'capture'),
    ('csv-import', 'marker-import-threshold-before-20261007-v1', 'freeze_marker_import_threshold_20261007.py', 'capture'),
)
CAPABILITY_PREFIXES = {
    'PyFLASH.markers.Antibody.clean_df': ('marker-threshold.constructor.',),
    'PyFLASH.markers.Antibody.addColocData': ('marker-threshold.constructor.',),
    'PyFLASH.markers.Antibody.find_closest_distances_between_markers': ('marker-threshold.nearest.',),
    'PyFLASH.experiment.Experiment.importCSVs': ('marker-threshold.csv-import.',),
}
COMPLETE_CAPABILITIES = frozenset()


CACHE_CARRIER_SHA256 = '7ed5ae54cfbeaf98fee577aff327b81049bc39b8135f2a2eee5a5169485c80b6'


def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    verify_manifest(ARCHIVE, 'source-manifest.json', MANIFEST_SHA256, cache_carrier_sha256=CACHE_CARRIER_SHA256)



def cases():
    rows = []
    for kind, owner, producer, function in SOURCES:
        frozen = json.loads((ARCHIVE / owner / 'frozen-before.json').read_text(encoding='utf-8'))
        for ref in frozen['rows']:
            rows.append({'key': 'marker-threshold.' + kind + '.' + ref['case']['key'], 'kind': kind, 'owner': owner, 'producer': producer, 'function': function, 'reference': ref})
    return rows


def required_keys(capability):
    prefixes = CAPABILITY_PREFIXES.get(capability, ())
    return {row['key'] for row in cases() if any(row['key'].startswith(prefix) for prefix in prefixes)}


def _caller(item):
    from types import SimpleNamespace
    import contextlib
    import io
    import warnings
    import numpy as np
    import pandas as pd
    from PyFLASH import markers
    from PyFLASH.config import Config
    from PyFLASH.experiment import Experiment
    source = ARCHIVE / item['owner'] / item['producer']
    tree = ast.parse(source.read_text(encoding='utf-8'))
    fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == item['function'])
    scope = dict(globals(), SimpleNamespace=SimpleNamespace, contextlib=contextlib, io=io, warnings=warnings, np=np, pd=pd, markers=markers, Config=Config, Experiment=Experiment)
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(source), 'exec'), scope)
    return scope[fn.name]


def check_result(item, actual):
    case = item['reference']['case']
    if item['kind'] == 'nearest':
        assert actual['actual'] == item['reference']['expected'], item['key']
        return
    assert actual['actual'] == case['expected'], item['key']
    assert actual['stored_threshold'] == case['requested_threshold']
    if item['kind'] == 'csv-import':
        assert actual['returned_own_data']
        prior = item['reference']['production']['table']
    else:
        prior = item['reference']['table']
    table = actual['table']
    revised = {'A_VolColocCountB', 'A_CPCColocCountB', 'A_ColocCountB', 'A_NonColocCountB'}
    old_columns = ['A_VolColoc_B' if name == 'A_ColocB' else name for name in prior['columns']]
    new_columns = table['columns']
    assert table['index'] == prior['index'] and table['index_name'] == prior['index_name']
    expected_added = [] if case['family'] != 'legacy' else ['A_VolColocCountB', 'A_ColocCountB', 'A_NonColocCountB']
    assert new_columns == old_columns + expected_added
    for i, name in enumerate(old_columns):
        j = new_columns.index(name)
        assert table['dtypes'][j] == prior['dtypes'][i]
        if name not in revised:
            assert [row[j] for row in table['values']] == [row[i] for row in prior['values']], (item['key'], name)
    for name in revised & set(new_columns):
        j = new_columns.index(name)
        expected = [1 - value for value in case['expected']] if name == 'A_NonColocCountB' else case['expected']
        assert [row[j] for row in table['values']] == expected, (item['key'], name)
        assert table['dtypes'][j] == 'int8'


def production(item, observation):
    caller = _caller(item)
    case = item['reference']['case']
    if item['kind'] == 'csv-import':
        actual = caller(case, (ARCHIVE / item['owner'] / item['reference']['input']).parent.parent)
    else:
        actual = caller(case)
    observation.update(production=actual, reference=item['reference'])
    check_result(item, actual)
    return actual, item['reference'], 'Literal independently declared threshold/binary/naming/table contracts', 'Functional option controls only; complete scientific marker and import methods remain open.'


def validate(output):
    check_identity()
    from reproducibility.normality_association_validation import comparison
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for item in cases():
        observation = {}
        try:
            actual, answer, reference, scope = production(item, observation)
            rows.append(comparison(item['key'], reference, 'functional-marker-threshold', actual, answer, True, True, scope, 0, 0))
        except Exception as exc:
            rows.append(comparison(item['key'], 'Literal threshold/constructor/import contract', 'functional-marker-threshold', observation.get('production'), observation.get('reference'), False, True, type(exc).__name__ + ': ' + str(exc), 0, 0))
    (output / 'marker-threshold-paired.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    return rows
