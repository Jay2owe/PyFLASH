"""Replay original flat CSV lifecycle tables without certifying acquired images."""
from pathlib import Path
import json

ARCHIVE = Path(__file__).with_name('reference-sources') / 'mini-lifecycle-native'
MANIFEST_SHA256 = '0c2a4c09495bc9a9796fc11826c16128a04ec21dd39da2a7e230dd1a26be84e7'
CAPABILITY_PREFIXES = {name: ('mini-lifecycle.',) for name in (
    'PyFLASH.experiment.MiniExperiment.importCSVs',
    'PyFLASH.experiment.MiniExperiment.createSummary',
    'PyFLASH.experiment.MiniExperiment.set_condition_list',
    'PyFLASH.experiment.MiniExperiment.processData')}
COMPLETE_CAPABILITIES = frozenset()


def read(name):
    return json.loads((ARCHIVE / name).read_text(encoding='utf-8'))


def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    from reproducibility import mini_lifecycle_reference as reference
    verify_manifest(ARCHIVE, 'source-files.json', MANIFEST_SHA256)
    if Path(reference.__file__).read_bytes() != (ARCHIVE / 'lifecycle_reference.py').read_bytes():
        raise ValueError('Original flat CSV lifecycle reference changed.')
    if [row['case'] for row in read('lifecycle-original/before.json')['rows']] != list(reference.cases()):
        raise ValueError('Original flat CSV lifecycle inputs changed.')


def cases():
    numerical = [dict(key='mini-lifecycle.' + row['case']['key'], kind='table', case=row['case'],
                      expected=row['expected'], raw_expected=row['raw_expected'])
                 for row in read('lifecycle-original/before.json')['rows']]
    refusals = [dict(key='mini-lifecycle.refusal.' + row['conflict'] + '.' + str(row['progress']),
                     kind='refusal', case=row)
                for row in read('lifecycle-refusals-qualified.json')['cases']]
    return numerical + refusals


def refusal_production(item, observation=None):
    import contextlib
    import io
    import pandas as pd
    from PyFLASH.experiment import MiniExperiment
    from PyFLASH.markers import Attribute
    from PyFLASH.conditions import condition, conditionList
    from reproducibility.scientific_utility_contract import table
    case = item['case']
    conflict, progress = case['conflict'], case['progress']
    experiment = MiniExperiment('Conflicting subject factors', str(ARCHIVE))
    data = pd.DataFrame({'AnimalName': ['A1', 'A1', 'B2'],
        'Treatment': ['Control', 'Treated' if conflict == 'within-table' else 'Control', 'Treated'],
        'Value': [1., 3., 5.]})
    experiment.data = {'Data': Attribute('Data', data, experiment)}
    if conflict == 'across-tables':
        other = pd.DataFrame({'AnimalName': ['A1', 'B2'], 'Treatment': ['Treated', 'Treated'], 'Other': [2., 6.]})
        experiment.data['Other'] = Attribute('Other', other, experiment)
        experiment.summary = pd.DataFrame({'AnimalName': ['A1', 'B2'], 'Treatment': ['Control', 'Treated'], 'Condition': ['A', 'B']})
        experiment.summaries = {'SCN': experiment.summary}
    else:
        with contextlib.redirect_stdout(io.StringIO()):
            experiment.createSummary(progress=progress)
        if conflict == 'existing-summary':
            experiment.summary.loc[0, 'Treatment'] = 'Treated'
    original = {name: table(value.df) for name, value in experiment.data.items()}
    aliases = {name: value.df for name, value in experiment.data.items()}
    summary = experiment.summary
    original_summary = table(summary)
    fields = {key: experiment.__dict__.get(key) for key in ('condition_list', 'conditions', 'factor', 'factorDict')}
    present = {key: key in experiment.__dict__ for key in fields}
    conditions = conditionList([condition('Control', 'Control', None, 'Treatment'),
                                condition('Treated', 'Treated', None, 'Treatment')])
    refused = False
    try:
        experiment.set_condition_list(conditions)
    except ValueError as error:
        assert 'conflicting' in str(error)
        refused = True
    unchanged = (experiment.summary is summary and table(summary) == original_summary
        and original == {name: table(value.df) for name, value in experiment.data.items()}
        and all(value.df is aliases[name] for name, value in experiment.data.items())
        and all((key in experiment.__dict__) == present[key] and experiment.__dict__.get(key) is value for key, value in fields.items()))
    actual = dict(refused=refused, state_unchanged=unchanged)
    expected = dict(refused=True, state_unchanged=True)
    if observation is not None:
        observation.update(actual=actual, expected=expected)
    assert actual == expected
    return actual, expected


def production(item, output, observation=None):
    if item['kind'] == 'refusal':
        return refusal_production(item, observation)
    from reproducibility import mini_lifecycle_reference as reference
    from reproducibility.reference_runtime import values
    from reproducibility.scientific_utility_contract import table
    original = next(row for row in read('lifecycle-original/before.json')['rows'] if row['case'] == item['case'])
    expected, raw = reference.expected(item['case'], values(original['native']))
    assert table(expected) == item['expected']
    assert {name: table(frame) for name, frame in raw.items()} == item['raw_expected']
    result = reference.production(item['case'], expected, raw, Path(output))
    if observation is not None:
        observation.update(actual=result, expected=item['expected'], raw_expected=item['raw_expected'])
    assert result['passed'], result.get('error')
    return result, item['expected']


def validate(output):
    from reproducibility import mini_lifecycle_reference as reference
    from reproducibility.reference_runtime import execute_queries
    check_identity()
    original = read('lifecycle-original/native/flat-csv-lifecycle-queries.json')
    assert [reference.query(item['case']) for item in cases() if item['kind'] == 'table'] == original
    native = execute_queries(original, Path(output) / 'mini-lifecycle-native', name='flat-csv-lifecycle')
    retained = read('lifecycle-original/native/flat-csv-lifecycle-results.json')
    assert native['rows'] == retained['rows']
    from reproducibility.table_family_validation import replay
    return replay(cases(), lambda item, observed, path: production(item, path, observed), output,
        reference=lambda item: 'Original native R CSV means and full subject-factor ownership' if item['kind'] == 'table'
                              else 'Declared factor consistency and unchanged-state refusal policy',
        family='native-full-csv-tables/declared-atomic-condition-refusal',
        shape='every-summary-raw-table-factor-input-and-condition-state-field')
