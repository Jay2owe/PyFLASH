"""Replay complete excluded-measurement tables without certifying other routes."""
from pathlib import Path
import json

ARCHIVE = Path(__file__).with_name('reference-sources') / 'mini-exclusions-native'
MANIFEST_SHA256 = '5d0ce12bc7240f932c6aec3f053578f6aa1859dd80216f6eb92b5e7c60ea625b'
CAPABILITY_PREFIXES = {
    'PyFLASH.experiment.MiniExperiment.createSummary': ('mini-exclusions.',),
}
COMPLETE_CAPABILITIES = frozenset()


def read(name):
    return json.loads((ARCHIVE / name).read_text(encoding='utf-8'))


def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    from reproducibility import mini_exclusion_reference as reference
    verify_manifest(ARCHIVE, 'source-files.json', MANIFEST_SHA256)
    if Path(reference.__file__).read_bytes() != (ARCHIVE / 'exclusion_reference.py').read_bytes():
        raise ValueError('Original excluded-measurement reference changed.')
    if [row['case'] for row in read('original/before.json')['rows']] != list(reference.cases()):
        raise ValueError('Original excluded-measurement inputs changed.')


def cases():
    return [dict(key='mini-exclusions.' + row['case']['key'], case=row['case'], expected=row['expected'])
            for row in read('original/before.json')['rows']]


def production(item, observation=None):
    from reproducibility import mini_exclusion_reference as reference
    original = next(row for row in read('original/before.json')['rows'] if row['case'] == item['case'])
    from reproducibility.reference_runtime import values
    expected = reference.expected(item['case'], values(original['native']))
    assert reference.encoded(expected) == item['expected']
    result = reference.production(item['case'], expected)
    if observation is not None:
        observation.update(actual=result, expected=item['expected'])
    assert result['passed'], result.get('error')
    return result, item['expected']


def validate(output):
    from reproducibility import mini_exclusion_reference as reference
    from reproducibility.reference_runtime import execute_queries
    check_identity()
    original = read('original/native/excluded-measurement-means-queries.json')
    assert [reference.query(item['case']) for item in cases()] == original
    native = execute_queries(original, Path(output) / 'mini-exclusions-native',
                             name='excluded-measurement-means')
    retained = read('original/native/excluded-measurement-means-results.json')
    assert native['rows'] == retained['rows']
    from reproducibility.table_family_validation import replay
    return replay(cases(), lambda item, observed, path: production(item, observed), output,
        reference='Original native R mean and protected metadata policy',
        family='native-exclusion/full-public-table-and-metadata',
        shape='every-summary-field-original-input-dtype-and-return-ownership', rtol=1e-14)
