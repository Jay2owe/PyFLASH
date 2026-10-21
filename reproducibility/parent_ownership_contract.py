"""Literal factor assignment and collision-free original batch table ownership."""
from pathlib import Path
import json

ARCHIVE = Path(__file__).with_name('reference-sources') / 'parent-condition-and-table-ownership-native'
MANIFEST_SHA256 = '7f153643f8a86c8d3fa5f7ec4274e00af2b79f12bf305f9b428d83dc25437129'
COMPLETE_CAPABILITIES = frozenset()
CAPABILITY_PREFIXES = {
    'PyFLASH.experiment.Experiment.set_condition_list': ('literal-factors.',),
    'PyFLASH.experiment.MiniExperiment.set_condition_list': ('literal-factors.',),
}


def read(name):
    return json.loads((ARCHIVE / name).read_text(encoding='utf-8'))


def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    from reproducibility import parent_condition_reference as labels, batch_table_names_reference as names
    verify_manifest(ARCHIVE, 'source-files.json', MANIFEST_SHA256)
    for module, original in ((labels, 'parent_condition_reference_v2.py'), (names, 'batch_table_names_reference.py')):
        assert Path(module.__file__).read_bytes() == (ARCHIVE / original).read_bytes()
    assert list(labels.cases()) == [row['case'] for row in read('parent-conditions-original-v2/before.json')['rows']]
    assert list(names.cases()) == [row['case'] for row in read('batch-names-original/before.json')['rows']]


def cases():
    labels = [dict(key='literal-factors.' + row['case']['key'], kind='labels', case=row['case'],
                   expected=row['expected'], raw_expected=row['raw_expected'])
              for row in read('parent-conditions-original-v2/before.json')['rows']]
    names = [dict(key='batch-table-names.' + row['case']['key'], kind='names', case=row['case'],
                  expected=row['expected_names']) for row in read('batch-names-original/before.json')['rows']]
    return labels + names


def production(item, observation=None):
    from reproducibility import parent_condition_reference as labels, batch_table_names_reference as names
    from reproducibility.reference_runtime import values
    if item['kind'] == 'labels':
        original = next(row for row in read('parent-conditions-original-v2/before.json')['rows'] if row['case'] == item['case'])
        expect, raw = labels.expected(item['case'], values(original['native']))
        assert labels.table(expect) == original['expected'] == item['expected']
        assert labels.table(raw) == original['raw_expected'] == item['raw_expected']
        result = labels.production(item['case'], values(original['native']))
    else:
        original = next(row for row in read('batch-names-original/before.json')['rows'] if row['case'] == item['case'])
        assert item['expected'] == original['expected_names'] == values(original['native'])
        result = names.production(item['case'], item['expected'])
    if observation is not None:
        observation.update(actual=result, expected=item['expected'])
    assert result['passed'], result.get('error')
    return result, item['expected']


def validate(output):
    from reproducibility import parent_condition_reference as labels, batch_table_names_reference as names
    from reproducibility.reference_runtime import execute_queries
    from reproducibility.table_family_validation import replay
    check_identity()
    for module, folder, stem in ((labels, 'parent-conditions-original-v2', 'literal-factor-labels'),
                                (names, 'batch-names-original', 'batch-table-unique-names')):
        queries = [module.query(case) for case in module.cases()]
        assert queries == read(folder + '/native/' + stem + '-queries.json')
        native = execute_queries(queries, Path(output) / 'native' / stem, name=stem)
        assert native['rows'] == read(folder + '/native/' + stem + '-results.json')['rows']
    return replay(cases(), lambda item, observed, path: production(item, observed), output,
        reference=lambda item: ('Native R fixed literal matching; every parent summary and raw field'
            if item['kind'] == 'labels' else 'Native R make.unique; every original table and carrier identity; batch orchestration remains separately gated'),
        family='native-R/literal-factor-and-table-name-ownership',
        shape='full-table-fields-dtypes-aliases-no-overwritten-carriers')
