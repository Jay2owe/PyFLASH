"""Empty parent tables: native zero-row shapes and full functional ownership."""
from pathlib import Path
import json

ARCHIVE = Path(__file__).with_name('reference-sources') / 'empty-parent-tables-native'
MANIFEST_SHA256 = 'c5aba8d2e4cf3df668368dd65e6ce2eb5f509a0b6cc6aa82e33a8719f444e163'
AMENDMENT = ARCHIVE.with_name('empty-batch-marker-storage-amendment')
AMENDMENT_SHA256 = '7e6132695346a9676fd8ae0fc80c4058e28b4f84f084e1a16f812dc423e1331c'
COMPLETE_CAPABILITIES = frozenset()
CAPABILITY_PREFIXES = {
    'PyFLASH.experiment.Experiment.set_condition_list': ('empty-parent.',),
    'PyFLASH.experiment.MiniExperiment.set_condition_list': ('empty-parent.',),
    'PyFLASH.batch.Batch.processData': ('empty-parent.',),
}


def read(name):
    return json.loads((ARCHIVE / name).read_text(encoding='utf-8'))


def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    from reproducibility import empty_parent_reference as reference
    verify_manifest(ARCHIVE, 'source-files.json', MANIFEST_SHA256)
    verify_manifest(AMENDMENT, 'source-files.json', AMENDMENT_SHA256)
    assert Path(reference.__file__).read_bytes() == (AMENDMENT / 'accepted-reference.py').read_bytes()
    assert (AMENDMENT / 'original-installed-reference.py').read_bytes() == (ARCHIVE / 'empty_parent_reference_v2_20261008.py').read_bytes()
    assert list(reference.cases()) == [row['case'] for row in read('original-v2/before.json')['rows']]


def cases():
    return [dict(key='empty-parent.' + row['case']['key'], case=row['case'], expected=row['expected'])
            for row in read('original-v2/before.json')['rows']]


def production(item, output, observation=None):
    from reproducibility import empty_parent_reference as reference
    from reproducibility.reference_runtime import values
    original = next(row for row in read('original-v2/before.json')['rows'] if row['case'] == item['case'])
    answers = values(original['native'])
    assert item['expected'] == original['expected'] == reference.table(reference.expected(item['case'], answers))
    result = reference.production(item['case'], answers, output)
    if observation is not None:
        observation.update(actual=result, expected=item['expected'])
    assert result['passed'], result.get('error')
    return result, item['expected']


def validate(output):
    from reproducibility import empty_parent_reference as reference
    from reproducibility.reference_runtime import execute_queries
    from reproducibility.table_family_validation import replay
    check_identity()
    queries = [reference.query(case) for case in reference.cases()]
    assert queries == read('original-v2/native/empty-parent-tables-queries.json')
    native = execute_queries(queries, Path(output) / 'native', name='empty-parent-tables')
    assert native['rows'] == read('original-v2/native/empty-parent-tables-results.json')['rows']
    return replay(cases(), lambda item, observed, path: production(item, path, observed), output,
        reference='Native R empty table/matching shapes + literal Python schema and ownership; functional only, no numerical vote',
        family='functional-empty-parent-tables', shape='all-empty-summary-raw-fields-dtypes-aliases-and-batch-state')
