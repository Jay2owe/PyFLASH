"""Complete direct assignment contract; functional ownership, no science vote."""
from pathlib import Path
import json

ARCHIVE = Path(__file__).with_name('reference-sources') / 'marker-table-assignment'
MANIFEST_SHA256 = 'e01865290431fe98c373c915aa5ed6b070c2be1335b7a8d4aec87efef764b773'
COMPLETE_CAPABILITIES = frozenset(
    f'PyFLASH.markers.{owner}.set_df'
    for owner in ('Antibody', 'objectMarker', 'cellMarker')
)
CAPABILITY_PREFIXES = {
    capability: (('marker-assignment.',) if '.Antibody.' in capability else
                 (f"marker-assignment.{capability.split('.')[-2]}.",))
    for capability in COMPLETE_CAPABILITIES
}


def read(name):
    return json.loads((ARCHIVE / name).read_text(encoding='utf-8'))


def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    from reproducibility import marker_assignment_reference as reference
    verify_manifest(ARCHIVE, 'source-files.json', MANIFEST_SHA256)
    assert Path(reference.__file__).read_bytes() == (ARCHIVE / 'marker_assignment_reference_20261008.py').read_bytes()
    assert reference.cases() == [row['case'] for row in read('before.json')['rows']]


def cases():
    return [dict(key='marker-assignment.' + row['case']['key'], case=row['case'], expected=row['expected'])
            for row in read('before.json')['rows']]


def required_keys(capability):
    if capability not in COMPLETE_CAPABILITIES:
        return set()
    owner = capability.split('.')[-2]
    # Retain all 72 original Antibody obligations; each inherited exposure also
    # requires its 24 actual subclass calls, rather than inheriting evidence.
    return {item['key'] for item in cases()
            if owner == 'Antibody' or item['case']['owner'] == owner}


def production(item, observation=None):
    from reproducibility import marker_assignment_reference as reference
    original = next(row for row in read('before.json')['rows'] if row['case'] == item['case'])
    assert item['expected'] == original['expected'] == reference.EXPECTED
    actual = reference.production(item['case'])
    if observation is not None:
        observation.update(actual=actual, expected=item['expected'])
    assert actual == item['expected']
    return actual, item['expected']


def validate(output):
    from reproducibility.table_family_validation import replay
    check_identity()
    return replay(cases(), lambda item, observed, path: production(item, observed), output,
        reference='Literal direct assignment, caller identity and unchanged complete carriers; functional only, no independent numerical vote',
        family='functional-marker-table-assignment', shape='all-return-and-state-identities-and-unchanged-full-carriers')
