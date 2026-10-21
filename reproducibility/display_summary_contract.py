"""Whole display getter contract: literal presentation and unchanged ownership."""
from pathlib import Path
import json

ARCHIVE = Path(__file__).with_name('reference-sources') / 'display-summary-functional'
MANIFEST_SHA256 = '8a23c12d780fef371b4a617dd2949fe9a8cab2ef7d27b4682aecabccf375427d'
COMPLETE_CAPABILITIES = frozenset({
    'PyFLASH.experiment.Experiment.getDisplaySummary',
    'PyFLASH.experiment.MiniExperiment.getDisplaySummary',
    'PyFLASH.batch.Batch.getDisplaySummary',
})
CAPABILITY_PREFIXES = {capability: ('display-summary.' + capability.split('.')[-2] + '.',)
                       for capability in COMPLETE_CAPABILITIES}


def read(name):
    return json.loads((ARCHIVE / name).read_text(encoding='utf-8'))


def check_identity():
    from reproducibility import display_summary_reference as reference
    from reproducibility.evidence_identity import verify_manifest
    verify_manifest(ARCHIVE, 'source-files.json', MANIFEST_SHA256)
    assert Path(reference.__file__).read_bytes() == (
        ARCHIVE / 'original-0-display_summary_whole_reference_20261008.py').read_bytes()
    original = read('before.json')
    assert original['actual_calls'] == 240 and not original['failed'] and not original['source_changes']
    assert reference.cases() == [row['case'] for row in original['rows']]


def cases():
    return [dict(key='display-summary.' + row['case']['key'], case=row['case'], expected=row['expected'])
            for row in read('before.json')['rows']]


def required_keys(capability):
    if capability not in COMPLETE_CAPABILITIES:
        return set()
    owner = capability.split('.')[-2]
    return {item['key'] for item in cases() if item['case']['owner'] == owner}


def production(item, observation=None):
    from reproducibility import display_summary_reference as reference
    original = next(row for row in read('before.json')['rows'] if row['case'] == item['case'])
    assert original['expected'] == item['expected']
    result = reference.production(item['case'])
    if observation is not None:
        observation.update(actual=result.get('actual'), expected=item['expected'])
    assert result['passed'], result.get('error')
    assert result['expected'] == result['actual'] == item['expected']
    return result['actual'], item['expected']


def validate(output):
    from reproducibility.table_family_validation import replay
    check_identity()
    return replay(cases(), lambda item, observed, path: production(item, observed), output,
        reference='Audit-authored literal labels, ROI selection, whole-table values/types/metadata and copy ownership; functional presentation only, no numerical science vote',
        family='functional-display-summary', shape='complete-returned-table-selection-and-original-state')
