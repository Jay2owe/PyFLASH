"""Whole image-table retrieval, refresh, real directory indexing and ownership."""
from pathlib import Path
from functools import lru_cache
import copy
import json

ARCHIVE = Path(__file__).with_name('reference-sources') / 'whole-image-tables'
MANIFEST_SHA256 = '18de94d62dedbc1cc3406150ccf9bd1b433641c9958e69e8d314e79147189e0d'
CAPABILITIES = frozenset({
    'PyFLASH.experiment.Experiment.getImageTable',
    'PyFLASH.experiment.MiniExperiment.getImageTable',
    'PyFLASH.batch.Batch.getImageTable',
})
COMPLETE_CAPABILITIES = CAPABILITIES
CAPABILITY_PREFIXES = {capability: tuple('image-table.' + group + '.' + capability.split('.')[-2] + '.'
    for group in ('original', 'identity-edges', 'real-import')) for capability in CAPABILITIES}


@lru_cache(maxsize=16)
def _retained(path):
    return json.loads(path.read_text(encoding='utf-8'))


def read(name):
    return _retained((ARCHIVE / name).resolve())


def modules():
    from reproducibility import image_table_reference, image_table_edge_reference, image_table_import_reference
    return {'original': image_table_reference, 'identity-edges': image_table_edge_reference.load(),
            'real-import': image_table_import_reference}


def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    from reproducibility import image_table_reference, image_table_edge_reference, image_table_import_reference
    verify_manifest(ARCHIVE, 'source-files.json', MANIFEST_SHA256)
    assert Path(image_table_reference.__file__).read_bytes() == (
        ARCHIVE / 'original/original-2-image_table_whole_reference_20261008_v2.py').read_bytes()
    assert Path(image_table_import_reference.__file__).read_bytes() == (
        ARCHIVE / 'real-import/original-2-image_table_real_import_reference_20261008_v2.py').read_bytes()
    edge = (ARCHIVE / 'identity-edges/original-3-image_table_identity_edges_20261008.py').read_text(encoding='utf-8')
    portable = edge.replace("SOURCE = Path('.runtime/image_table_whole_reference_20261008_v2.py')",
        'from reproducibility import image_table_reference as retained_reference\nSOURCE = Path(retained_reference.__file__)')
    assert Path(image_table_edge_reference.__file__).read_text(encoding='utf-8') == portable
    loaded = modules()
    for group, count, failures in (('original', 360, 42), ('identity-edges', 216, 54), ('real-import', 108, 36)):
        before = read(group + '/before.json')
        assert before['actual_calls'] == count and before['failed'] == failures and not before['source_changes']
        assert [row['case'] for row in before['rows']] == read(group + '/inputs.json')
        for source, digest in before['sources'].items():
            if Path(source).name == 'experiment.py':
                import hashlib
                assert hashlib.sha256((ARCHIVE / group / 'original-0-experiment.py').read_bytes()).hexdigest() == digest
        if group != 'real-import':
            for row in before['rows']:
                assert loaded[group].table(loaded[group].expected(row['case'])) == row['expected']
    assert [row['expected'] for row in read('real-import/before.json')['rows']] == [
        row['expected'] for row in read('real-import-first/before.json')['rows']]
    amendment = read('real-import/observation-amendment.json')
    assert amendment['original_prediction_unchanged'] and amendment['original_calls'] == 108
    qualified = read('private-whole/run.json')
    assert qualified['passed'] and qualified['actual_getter_calls'] == 684
    assert qualified['whole_assignment_controls'] == 864 and qualified['existing_controls'] == 536
    assert not qualified['source_changes'] and read('installation/installation.json')['passed']


def cases():
    return [dict(key='image-table.' + group + '.' + row['case']['key'], group=group,
        case=copy.deepcopy(row['case']), expected=copy.deepcopy(row['expected']))
        for group in ('original', 'identity-edges', 'real-import') for row in read(group + '/before.json')['rows']]


def required_keys(capability):
    if capability not in CAPABILITIES:
        return set()
    return {item['key'] for item in cases() if item['case']['owner'] == capability.split('.')[-2]}


def production(item, directory, observation=None):
    before = next(row for row in read(item['group'] + '/before.json')['rows'] if row['case'] == item['case'])
    assert item['expected'] == before['expected']
    observed = modules()[item['group']].production(item['case'], Path(directory))
    if observation is not None:
        observation.update(actual=observed['actual'], expected=item['expected'])
    assert observed['passed'], observed.get('error')
    assert observed['actual'] == observed['expected'] == item['expected']
    return observed['actual']


def validate(output):
    from reproducibility.table_family_validation import replay
    check_identity()
    return replay(cases(), lambda item, observed, path: production(item, path, observed), output,
        reference='Literal acquired fields and separately executed SQLite first-owned metadata lookup; real authored directory indexing; functional retrieval only, no pixel-decoder or numerical scientific-method vote',
        family='functional-whole-image-tables',
        shape='complete-returned-and-stored-tables-identity-types-indexes-attributes-and-caller-nested-ownership')
