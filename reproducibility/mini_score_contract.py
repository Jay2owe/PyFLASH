"""Replay complete marker score tables while retaining original native outliers."""
from pathlib import Path
import json
import math

ARCHIVE = Path(__file__).with_name('reference-sources') / 'mini-scores-native'
MANIFEST_SHA256 = '12a7de25d2a9517c4a4f7fef4f5283dcddd7ea5c0d316f40511b445666d2db60'
CAPABILITY_PREFIXES = {'PyFLASH.experiment.MiniExperiment.createSummary': ('mini-scores.',)}
COMPLETE_CAPABILITIES = frozenset()


def read(name):
    return json.loads((ARCHIVE / name).read_text(encoding='utf-8'))


def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    from reproducibility import mini_score_reference as reference
    verify_manifest(ARCHIVE, 'source-files.json', MANIFEST_SHA256)
    if Path(reference.__file__).read_bytes() != (ARCHIVE / 'score_reference_v2.py').read_bytes():
        raise ValueError('Original marker score reference changed.')
    if [row['case'] for row in read('scores-reference-v2/before.json')['rows']] != list(reference.cases()):
        raise ValueError('Original marker score inputs changed.')


def cases():
    return [dict(key='mini-scores.' + row['case']['key'], case=row['case'], expected=row['expected'])
            for row in read('scores-qualified-v2.json')['rows']]


def production(item, observation=None):
    from reproducibility import mini_score_reference as reference
    from reproducibility.reference_runtime import values
    from reproducibility.scientific_utility_contract import table
    original = next(row for row in read('scores-reference-v2/before.json')['rows'] if row['case'] == item['case'])
    expected = reference.expected(item['case'], values(original['native']))
    expected['M_burdenScore'] = expected['M_burdenScore'].astype(float)
    expected['M_fragmentationScore'] = expected['M_fragmentationScore'].astype(float)
    assert table(expected) == item['expected']
    result = reference.production(item['case'], expected)
    if observation is not None:
        observation.update(actual=result, expected=item['expected'])
    assert result['passed'], result.get('error')
    return result, item['expected']


def validate(output):
    from reproducibility import mini_score_reference as reference
    from reproducibility.reference_runtime import execute_queries, values
    check_identity()
    original = read('scores-reference-v2/native/marker-summary-scores-queries.json')
    assert [reference.query(item['case']) for item in cases()] == original
    native = execute_queries(original, Path(output) / 'mini-scores-native', name='marker-summary-scores')
    retained = read('scores-reference-v2/native/marker-summary-scores-results.json')
    assert native['rows'] == retained['rows']
    for item, row in zip(cases(), native['rows'], strict=True):
        for actual, independent in zip(values(row), reference.mp_scores(item['case']), strict=True):
            assert (math.isnan(actual) and math.isnan(independent)) or math.isclose(
                actual, independent, rel_tol=2e-12, abs_tol=2e-14), item['key']
    schema = read('scores-schema-amendment/native-score-storage-queries.json')
    checked = execute_queries(schema, Path(output) / 'mini-scores-native', name='native-score-storage')
    assert values(checked['rows'][0]) == ['double', 'double']
    from reproducibility.table_family_validation import replay
    return replay(cases(), lambda item, observed, path: production(item, observed), output,
        reference='Scaled published R scale and 4096-bit mpmath',
        family='independent-numerical-engine/native-scaled-standardization',
        shape='every-score-and-raw-summary-field-input-dtype-and-ownership', rtol=2e-12, atol=2e-14)
