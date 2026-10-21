"""Replay original exact object-storage means through full public summaries."""
from pathlib import Path
import json

ARCHIVE = Path(__file__).with_name('reference-sources') / 'mini-object-means-native'
MANIFEST_SHA256 = 'e72aefedd8fefd7f15655f013065e9c9f0b7e08c06b4f1835956355c6687b6db'
CAPABILITY_PREFIXES = {'PyFLASH.experiment.MiniExperiment.createSummary': ('mini-object-means.',)}
COMPLETE_CAPABILITIES = frozenset()


def read(name):
    return json.loads((ARCHIVE / name).read_text(encoding='utf-8'))


def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    from reproducibility import mini_object_mean_reference as reference
    verify_manifest(ARCHIVE, 'source-files.json', MANIFEST_SHA256)
    assert Path(reference.__file__).read_bytes() == (ARCHIVE / 'object_mean_reference.py').read_bytes()
    assert list(reference.cases()) == [row['case'] for row in read('original/before.json')['rows']]


def cases():
    return [dict(key='mini-object-means.' + row['case']['key'], case=row['case'], expected=row['expected'])
            for row in read('original/before.json')['rows']]


def production(item, folder, observation=None):
    from reproducibility import mini_object_mean_reference as reference
    original = next(row for row in read('original/before.json')['rows'] if row['case'] == item['case'])
    expected = reference.expected(item['case'])
    assert reference.table(expected) == original['expected'] == item['expected']
    result = reference.production(item['case'], expected, folder)
    if observation is not None:
        observation.update(actual=result, expected=item['expected'])
    assert result['passed'], result.get('error')
    return result, item['expected']


def validate(output):
    from reproducibility import mini_object_mean_reference as reference
    from reproducibility.reference_runtime import execute_queries
    from reproducibility.table_family_validation import replay
    check_identity()
    queries = [reference.query(item['case']) for item in cases()]
    assert queries == read('original/native/original-object-double-transport-queries.json')
    native = execute_queries(queries, Path(output) / 'native', name='original-object-double-transport')
    assert native['rows'] == read('original/native/original-object-double-transport-results.json')['rows']
    return replay(cases(), lambda item, observed, path: production(item, path, observed), output,
        reference='Original 4096-bit mpmath and 2048-digit Decimal exact represented-input means; R double transport retained separately',
        family='exact-object-storage/full-public-summary',
        shape='every-summary-field-dtype-input-alias-and-return-ownership')
