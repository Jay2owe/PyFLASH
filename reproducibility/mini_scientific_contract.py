"""Replay independent full MiniExperiment tables without certifying other routes.

Published native R/Python CSV parsers establish exact subject row identities.
Python statistics and mpmath independently establish extreme means. Original R
cancellation disagreements and original failed public outputs remain archived.
"""
from pathlib import Path
import contextlib
import hashlib
import io
import json
import math
import tempfile

ARCHIVE = Path(__file__).with_name('reference-sources') / 'mini-summary-native'
MANIFEST_SHA256 = '7a667332d59c4e862b13d42278a88e3bffbcbd4205b32f2b5d9859d90544bcb0'
FILES_SHA256 = 'fb0effa955b74f5d7cd047e4ae1b05e49e2af5428201373ead9cdf32a89358ae'
EXPERIMENT_FILES_SHA256 = '0cbdccb63ea7ad44519d511734cf3d99fc68d1cc8f73607833ee346be5e71893'
TYPED_FILES_SHA256 = 'e4d75bdba3898e3bbffc91dba8bff4de67af829cdc1c59805504827dc172b794'
CAPABILITY_PREFIXES = {
    'PyFLASH.experiment.MiniExperiment.createSummary': (
        'mini-scientific.mean.', 'mini-scientific.typed.',
        'mini-scientific.integer.', 'mini-scientific.integer-boundary.'),
    'PyFLASH.experiment.MiniExperiment.importCSVs': ('mini-scientific.identity.',),
    'PyFLASH.experiment.Experiment.createSummary': ('mini-scientific.experiment-mean.',),
}
COMPLETE_CAPABILITIES = frozenset()


def read(name):
    return json.loads((ARCHIVE / name).read_text(encoding='utf-8'))


def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    verify_manifest(ARCHIVE, 'source-files.json', FILES_SHA256)
    verify_manifest(ARCHIVE / 'experiment', 'source-files.json', EXPERIMENT_FILES_SHA256)
    verify_manifest(ARCHIVE / 'typed', 'source-files.json', TYPED_FILES_SHA256)
    if hashlib.sha256((ARCHIVE / 'source-manifest.json').read_bytes()).hexdigest() != MANIFEST_SHA256:
        raise ValueError('Retained MiniExperiment evidence manifest changed.')
    from reproducibility import mini_summary_reference, mini_identifier_reference
    for reference, original in ((mini_summary_reference, 'means/reference.py'),
                                (mini_identifier_reference, 'identifiers/reference.py')):
        if Path(reference.__file__).read_bytes() != (ARCHIVE / original).read_bytes():
            raise ValueError('Original MiniExperiment reference changed.')
    if [r['case'] for r in read('means/frozen.json')['rows']] != [
            dict(case, values=['Inf' if x == math.inf else '-Inf' if x == -math.inf else x
                               for x in case['values']]) for case in mini_summary_reference.cases()]:
        raise ValueError('Original mean inputs changed.')
    if [r['case'] for r in read('identifiers/before.json')['rows'][::2]] != mini_identifier_reference.cases():
        raise ValueError('Original CSV inputs changed.')


def cases():
    means = [{'key': 'mini-scientific.mean.' + row['key'], 'kind': 'mean',
              'case': row['case'], 'progress': row['progress'], 'expected': row['expected']}
             for row in read('means/before.json')['rows']]
    originals = read('identifiers/before.json')['rows']
    qualified = read('identifiers/qualified-v3.json')['rows']
    identities = [{'key': 'mini-scientific.identity.' + original['key'], 'kind': 'identity',
                   'case': original['case'], 'progress': original['progress'], 'expected': row['expected']}
                  for original, row in zip(originals, qualified, strict=True)]
    original_experiments = read('experiment/experiment-before.json')['rows']
    qualified_experiments = read('experiment/experiment-qualified.json')['rows']
    experiments = [{'key': 'mini-scientific.experiment-mean.' + original['key'], 'kind': 'experiment-mean',
                    'case': original['case'], 'progress': original['progress'], 'expected': row['expected'],
                    'input_tables': original['input_tables']}
                   for original, row in zip(original_experiments, qualified_experiments, strict=True)]
    typed = [{'key': 'mini-scientific.typed.' + row['key'] + '.' + str(progress), 'kind': 'typed',
              'dtype': row['dtype'], 'input': row['input'], 'represented': row['represented'],
              'progress': progress, 'expected': row['expected']}
             for row in read('typed/typed-v2/before.json')['rows'] for progress in (False, True)]
    integers = []
    for directory, kind in (('integers', 'integer'), ('integers-boundary', 'integer-boundary')):
        integers += [{'key': 'mini-scientific.' + kind + '.' + row['key'], 'kind': kind,
                      'dtype': row['dtype'], 'input': row['input'], 'represented': row['represented'],
                      'progress': row['progress'], 'expected': row['expected']}
                     for row in read('typed/' + directory + '/before.json')['rows']]
    return means + identities + experiments + typed + integers


def decode(value):
    if isinstance(value, str):
        return {'Inf': math.inf, '-Inf': -math.inf, 'NaN': math.nan}.get(value, value)
    return value


def typed_production(item, observation=None):
    import pandas as pd
    from PyFLASH.experiment import MiniExperiment
    from PyFLASH.markers import Attribute
    from reproducibility.scientific_utility_contract import table
    def token(value):
        if value is pd.NA:
            return 'pd.NA'
        raise TypeError('Unexpected reference transport type: ' + type(value).__name__)
    def encoded(frame):
        return json.loads(json.dumps(table(frame), default=token))
    numbers = [pd.NA if row[1] == 'pd.NA' else decode(row[1]) for row in item['input']['rows']]
    frame = pd.DataFrame({'AnimalName': ['Subject1'] * len(numbers), 'Value': pd.Series(numbers, dtype=item['dtype'])})
    experiment = MiniExperiment('Independent numeric storage controls', str(ARCHIVE))
    carrier = Attribute('Data', frame, experiment)
    experiment.data = {'Data': carrier}
    original_mapping, original_frame = experiment.data, carrier.df
    original = encoded(carrier.df)
    result = experiment.createSummary(progress=item['progress'])
    actual = {'table': encoded(result), 'input_unchanged': encoded(carrier.df) == original,
              'return_alias': result is experiment.summary and result is experiment.summaries['SCN'],
              'mapping_alias': experiment.data is original_mapping and experiment.data['Data'] is carrier,
              'carrier_alias': carrier.df is original_frame and carrier.experiment is experiment}
    expected = {'table': item['expected'], 'input_unchanged': True, 'return_alias': True,
                'mapping_alias': True, 'carrier_alias': True}
    if observation is not None:
        observation.update(actual=actual, expected=expected)
    assert actual == expected, item['key']
    return actual, expected


def production(item, observation=None, *, output=None):
    import pandas as pd
    from PyFLASH.experiment import MiniExperiment
    from PyFLASH.markers import Attribute
    from reproducibility.scientific_utility_contract import table
    if item['kind'] == 'experiment-mean':
        return experiment_production(item, observation)
    if item['kind'] in ('typed', 'integer', 'integer-boundary'):
        return typed_production(item, observation)
    with tempfile.TemporaryDirectory(prefix='pyflash-mini-contract-') as temporary:
        folder = Path(temporary)
        experiment = MiniExperiment('Independent table controls', str(folder),
                                    subject_column=item['case']['explicit'] if item['kind'] == 'identity' else None)
        if item['kind'] == 'mean':
            frozen = next(r['case'] for r in read('means/frozen.json')['rows'] if r['case']['key'] == item['case'])
            numbers = [math.nan if x is None else decode(x) for x in frozen['values']]
            carrier = Attribute('Data', pd.DataFrame({'AnimalName': ['Subject1'] * len(numbers), 'Value': numbers}), experiment)
            experiment.data = {'Data': carrier}
            original_table = table(carrier.df)
            original_mapping, original_frame = experiment.data, carrier.df
            result = experiment.createSummary(progress=item['progress'])
            actual = {'table': table(result), 'input_unchanged': table(carrier.df) == original_table,
                      'return_alias': result is experiment.summary and result is experiment.summaries['SCN'],
                      'mapping_alias': experiment.data is original_mapping and experiment.data['Data'] is carrier,
                      'carrier_alias': carrier.df is original_frame and carrier.experiment is experiment,
                      'summary_text': experiment._last_summary_summary}
            expected = {'table': item['expected'], 'input_unchanged': True, 'return_alias': True,
                        'mapping_alias': True, 'carrier_alias': True, 'summary_text': '1 subjects x 3 columns'}
        else:
            case = item['case']
            (folder / 'Data.csv').write_text(case['csv'], encoding='utf-8')
            if case['labels']:
                (folder / 'Condition Labels.csv').write_text(case['labels'], encoding='utf-8')
            source_bytes = {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()}
            mapping = experiment.data
            with contextlib.redirect_stdout(io.StringIO()):
                result = experiment.importCSVs(progress=item['progress'])
            actual = {'table': table(result['Data'].df), 'return_alias': result is mapping and result is experiment.data,
                      'carrier_alias': result['Data'].experiment is experiment, 'keys': list(result),
                      'input_unchanged': source_bytes == {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()},
                      'summary_text': experiment._last_csv_import_summary}
            expected = {'table': item['expected'], 'return_alias': True, 'carrier_alias': True,
                        'keys': ['Data'], 'input_unchanged': True, 'summary_text': '1 tables'}
        if observation is not None:
            observation.update(actual=actual, expected=expected)
        if output is not None:
            from PyFLASH._persistence import write_json
            write_json(Path(output) / (item['key'].replace('/', '_') + '.json'), {'actual': actual, 'expected': expected})
        assert actual == expected, item['key']
        return actual, expected


def experiment_production(item, observation=None):
    import pandas as pd
    from PyFLASH.experiment import Experiment
    from PyFLASH.markers import objectMarker
    from PyFLASH.dataframe import DataFrameTable
    from PyFLASH.config import Config
    from reproducibility.scientific_utility_contract import table
    def frame(encoded):
        result = pd.DataFrame([[decode(value) for value in row] for row in encoded['rows']],
                              columns=encoded['columns'], index=encoded['index'])
        return result.astype(dict(zip(encoded['columns'], encoded['dtypes'], strict=True)))
    experiment = Experiment.__new__(Experiment)
    experiment.name = 'Independent experiment mean controls'
    marker = objectMarker.__new__(objectMarker)
    marker.name = 'M'
    marker.df = frame(item['input_tables']['M'])
    props = DataFrameTable('ROI Properties', frame(item['input_tables']['ROI Properties']))
    experiment.data = {'M': marker, 'ROI Properties': props}
    mapping = experiment.data
    aliases = {key: value.df for key, value in mapping.items()}
    old = Config.SECTION_THICKNESS_UM
    try:
        Config.SECTION_THICKNESS_UM = 13.
        with contextlib.redirect_stdout(io.StringIO()):
            result = experiment.createSummary(progress=item['progress'])
    finally:
        Config.SECTION_THICKNESS_UM = old
    expected_frame = frame(item['expected'])
    actual = {'table': table(result['SCN']), 'return_alias': result is experiment.summaries,
              'keys': list(result), 'mapping_alias': experiment.data is mapping,
              'input_tables': {key: table(value.df) for key, value in mapping.items()},
              'carrier_alias': all(value.df is aliases[key] for key, value in mapping.items())}
    expected = {'table': item['expected'], 'return_alias': True, 'keys': ['SCN'], 'mapping_alias': True,
                'input_tables': item['input_tables'], 'carrier_alias': True}
    if observation is not None:
        observation.update(actual=actual, expected=expected)
    pd.testing.assert_frame_equal(result['SCN'], expected_frame, check_exact=False, rtol=1e-12, atol=0.)
    mean_column = 'M_Value' if item['case'] == 'all-missing' else 'M_ValueMean'
    left, right = float(result['SCN'].loc[0, mean_column]), float(expected_frame.loc[0, mean_column])
    assert left == right or math.isnan(left) and math.isnan(right)
    assert {key: value for key, value in actual.items() if key != 'table'} == {
        key: value for key, value in expected.items() if key != 'table'}
    return actual, expected


def validate(output):
    from reproducibility import mini_summary_reference as means, mini_identifier_reference as identities
    from reproducibility.reference_runtime import execute_queries, values
    from reproducibility.normality_association_validation import comparison
    from PyFLASH._persistence import write_json
    import mpmath
    check_identity()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    native_means = execute_queries([means.query(case) for case in means.cases()], output / 'native-means',
                                  name='mini-summary-means', timeout=180)
    frozen = read('means/frozen.json')
    outliers = []
    for case, original, native in zip(means.cases(), frozen['rows'], native_means['rows'], strict=True):
        number = values(native)[0]
        expected_native = decode(original['R'])
        assert number == expected_native or math.isnan(number) and math.isnan(expected_native)
        py = means.published_python_mean(case)
        inputs = [x for x in case['values'] if x is not None]
        with mpmath.workprec(4096):
            mp = float(mpmath.fsum(mpmath.mpf(x) for x in inputs) / len(inputs)) if inputs else math.nan
        expected = decode(original['python'])
        assert (py == mp == expected) or all(math.isnan(v) for v in (py, mp, expected))
        if number != expected and not (math.isnan(number) and math.isnan(expected)):
            outliers.append({'key': case['key'], 'R': original['R'], 'Python': original['python'],
                             'mpmath': mp, 'cause': 'Finite-precision cancellation in native R; original result retained.'})
    native_ids = execute_queries([identities.query(case) for case in identities.cases()], output / 'native-identities',
                                name='mini-csv-identifiers', timeout=180)
    for case, answer in zip(identities.cases(), native_ids['rows'], strict=True):
        assert answer['values'] == [row['AnimalName'] for row in identities.parsed(case)]
    original_indices = read('identifiers/native-index-amendment/mini-source-row-indices-queries.json')
    index_answers = execute_queries(original_indices, output / 'native-indices', name='mini-source-row-indices', timeout=180)
    retained_indices = read('identifiers/native-index-amendment/mini-source-row-indices-results.json')
    assert [r['values'] for r in index_answers['rows']] == [r['values'] for r in retained_indices['rows']]
    for result in (native_means, native_ids, index_answers):
        for key, value in frozen['runtime'].items():
            assert result[key] == value, key
    normalization_queries = read('experiment/native/experiment-mean-count-normalization-queries.json')
    normalization = execute_queries(normalization_queries, output / 'native-normalization',
                                    name='experiment-mean-count-normalization', timeout=180)
    original_normalization = read('experiment/native/experiment-mean-count-normalization-results.json')
    assert [r['values'] for r in normalization['rows']] == [r['values'] for r in original_normalization['rows']]
    from statistics import mean
    for directory, stem in (('typed-v2', 'typed-summary-means'),
                            ('integers', 'integer-summary-original-double-transport'),
                            ('integers-boundary', 'integer-summary-original-double-transport')):
        prefix = 'typed/' + directory + '/native/' + stem
        queries = read(prefix + '-queries.json')
        current = execute_queries(queries, output / ('native-' + directory), name=stem, timeout=180)
        original = read(prefix + '-results.json')
        assert [row['values'] for row in current['rows']] == [row['values'] for row in original['rows']]
        for key, value in frozen['runtime'].items():
            assert current[key] == value
    checked = set()
    for item in cases():
        if item['kind'] not in ('typed', 'integer', 'integer-boundary'):
            continue
        identity = json.dumps(item['represented'])
        if identity in checked:
            continue
        checked.add(identity)
        py = float(mean(item['represented']))
        with mpmath.workprec(4096):
            mp = float(mpmath.fsum(mpmath.mpf(value) for value in item['represented']) / len(item['represented']))
        assert py == mp
    paired, rows = [], []
    for item in cases():
        observation, error = {}, None
        try:
            production(item, observation)
        except Exception as failure:
            error = type(failure).__name__ + ': ' + str(failure)
        rows.append(comparison(item['key'],
                    'Independent mpmath means, Python statistics control and native-R normalization' if item['kind'] != 'identity' else 'Native R and Python CSV parsers',
                    'independent-numerical-engine/shared-rational-control/full-public-table-routing', observation.get('actual'), observation.get('expected'),
                    error is None, True, 'every-table-field-input-and-return-alias-in-recorded-routes',
                    1e-12 if item['kind'] == 'experiment-mean' else 0., 0.))
        paired.append({'item': item, **observation, 'error': error})
    write_json(output / 'mini-scientific-paired.json', paired)
    write_json(output / 'mini-native-mean-outliers.json', outliers)
    (output / 'MINI_DIFFERENCES.md').write_text(
        str(len(paired)) + ' recorded public table calls compared against unchanged references.\n\n'
        + '\n'.join(f"{r['key']}: R={r['R']}; Python={r['Python']}; mpmath={r['mpmath']}. {r['cause']}" for r in outliers)
        + '\n\nWhole import lifecycle and summary score/multi-table options remain partial.\n', encoding='utf-8')
    return rows
