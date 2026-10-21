"""Replay infinite observations without replacing undefined scores with zeros."""
from pathlib import Path
import json
import math

ARCHIVE = Path(__file__).with_name('reference-sources') / 'mini-nonfinite-scores-native'
MANIFEST_SHA256 = '70f175ae6458c4a0a014226af0f616e31ad5af0074ce011b78feaea1be9a06ac'
CAPABILITY_PREFIXES = {'PyFLASH.experiment.MiniExperiment.createSummary': ('mini-nonfinite-scores.',)}
COMPLETE_CAPABILITIES = frozenset()


def read(name):
    return json.loads((ARCHIVE / name).read_text(encoding='utf-8'))


def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    from reproducibility import mini_nonfinite_score_reference as reference
    verify_manifest(ARCHIVE, 'source-files.json', MANIFEST_SHA256)
    if Path(reference.__file__).read_bytes() != (ARCHIVE / 'score_reference_nonfinite.py').read_bytes():
        raise ValueError('Original infinite-observation score reference changed.')
    if [row['case'] for row in read('original/before.json')['rows']] != list(reference.cases()):
        raise ValueError('Original infinite-observation inputs changed.')


def cases():
    return [dict(key='mini-nonfinite-scores.' + row['case']['key'], case=row['case'], expected=row['expected'])
            for row in read('scores-nonfinite-qualified.json')['rows'] if row['kind'] == 'nonfinite']


def production(item, observation=None):
    from reproducibility import mini_nonfinite_score_reference as reference
    from reproducibility.reference_runtime import values
    from reproducibility.scientific_utility_contract import table
    original = next(row for row in read('original/before.json')['rows'] if row['case'] == item['case'])
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
    from reproducibility import mini_nonfinite_score_reference as reference
    from reproducibility.reference_runtime import execute_queries, values
    check_identity()
    original = read('original/native/marker-summary-scores-queries.json')
    assert [reference.query(item['case']) for item in cases()] == original
    native = execute_queries(original, Path(output) / 'mini-nonfinite-scores-native', name='marker-summary-scores')
    assert native['rows'] == read('original/native/marker-summary-scores-results.json')['rows']
    for item, row in zip(cases(), native['rows'], strict=True):
        for actual, independent in zip(values(row), reference.mp_scores(item['case']), strict=True):
            assert (math.isnan(actual) and math.isnan(independent)) or math.isclose(
                actual, independent, rel_tol=2e-12, abs_tol=2e-14), item['key']
    from reproducibility.table_family_validation import replay
    return replay(cases(), lambda item, observed, path: production(item, observed), output,
        reference='Published native R scale and 4096-bit mpmath with undefined infinities',
        family='independent-numerical-engine/native-undefined-standardization',
        shape='every-undefined-score-and-raw-observation-with-exact-missingness', rtol=2e-12, atol=2e-14)
