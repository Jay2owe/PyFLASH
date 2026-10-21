"""Whole declared categorical assignment, acquired tables and nested ownership."""
from pathlib import Path
from functools import lru_cache
import copy
import json

ARCHIVE = Path(__file__).with_name('reference-sources') / 'whole-parent-conditions'
MANIFEST_SHA256 = 'b9bf655b4ecba2c942ae2160fd8ce9fa873e00ad36beeb0f2c7ff0ed7a781e0b'
CAPABILITY = 'PyFLASH.experiment.Experiment.set_condition_list'
CAPABILITY_PREFIXES = {CAPABILITY: ('whole-parent-condition.',)}
COMPLETE_CAPABILITIES = frozenset({CAPABILITY})


@lru_cache(maxsize=8)
def _retained(path):
    return json.loads(path.read_text(encoding='utf-8'))


def read(name):
    return _retained((ARCHIVE / name).resolve())


def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    from reproducibility import whole_condition_reference as reference
    verify_manifest(ARCHIVE, 'source-files.json', MANIFEST_SHA256)
    assert Path(reference.__file__).read_bytes() == (ARCHIVE / 'original/original-reference.py').read_bytes()
    before = read('original/before.json')
    assert before['actual_calls'] == 864 and before['failed'] == 144 and before['source_unchanged']
    qualified = read('qualified/run.json')
    assert qualified['passed'] and qualified['actual_calls'] == 864 and qualified['existing_controls'] == 536
    assert list(reference.cases()) == [row['case'] for row in before['rows']]
    assert [reference.query(case) for case in reference.cases()] == read('native-original/whole-parent-factor-assignment-queries.json')
    assert read('native-original/whole-parent-factor-assignment-results.json')['rows'] == read('native-first-transport/whole-parent-factor-assignment-results.json')['rows']
    for row in before['rows']:
        summary, raw, images = reference.expected(row['case'], reference.values(row['native']))
        assert reference.table(summary) == row['expected']
        assert reference.table(raw) == row['raw_expected']
        assert (None if images is None else reference.table(images)) == row['images_expected']


def cases():
    return [dict(key='whole-parent-condition.' + row['case']['key'], case=copy.deepcopy(row['case']),
                 expected=copy.deepcopy({name: row[name] for name in ('expected', 'raw_expected', 'images_expected')}))
            for row in read('original/before.json')['rows']]


def required_keys(capability):
    if capability != CAPABILITY:
        return set()
    from reproducibility import empty_parent_contract
    return {item['key'] for item in cases()} | {item['key'] for item in empty_parent_contract.cases()
        if item['case']['kind'] == 'main'}


def production(item, observation=None):
    from PyFLASH.experiment import Experiment
    from reproducibility import whole_condition_reference as reference
    original = next(row for row in read('original/before.json')['rows'] if row['case'] == item['case'])
    predicted = {name: original[name] for name in ('expected', 'raw_expected', 'images_expected')}
    assert item['expected'] == predicted
    method = Experiment.set_condition_list
    def observe_ownership(self, conditions):
        images = self.imagesDict
        nested = copy.deepcopy(images)
        result = method(self, conditions)
        assert self.imagesDict is images and self.imagesDict == nested
        return result
    Experiment.set_condition_list = observe_ownership
    try:
        observed = reference.production(item['case'], reference.values(original['native']))
    finally:
        Experiment.set_condition_list = method
    actual = {name: observed[name] for name in ('summaries', 'raw', 'images')}
    expected = dict(summaries={roi: original['expected'] for roi in ('SCN', 'OC')[:item['case']['rois']]},
                    raw={str(index): original['raw_expected'] for index in range(3)},
                    images=original['images_expected'])
    if observation is not None:
        observation.update(actual=actual, expected=expected)
    assert observed['passed'], observed.get('error')
    assert actual == expected
    return actual


def validate(output):
    from reproducibility import whole_condition_reference as reference
    from reproducibility.reference_runtime import execute_queries
    from reproducibility.table_family_validation import replay
    check_identity()
    native = execute_queries([reference.query(case) for case in reference.cases()],
                             Path(output) / 'native', name='whole-parent-factor-assignment')
    assert native['rows'] == read('native-original/whole-parent-factor-assignment-results.json')['rows']
    return replay(cases(), lambda item, observed, path: production(item, observed), output,
        reference='Native R literal categorical matching and first-subject image ownership, complete authored measurements and literal Python aliases; functional assignment, no numerical-method vote',
        family='whole-parent-categorical-assignment', shape='every-summary-raw-and-image-cell-column-dtype-index-attribute-alias-and-nested-image-metadata')
