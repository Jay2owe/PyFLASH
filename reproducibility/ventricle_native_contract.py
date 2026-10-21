"""Whole public boundary tables against original native R and GEOS geometry."""
import contextlib
import hashlib
import io
import json
import math
from pathlib import Path
from types import SimpleNamespace

ARCHIVE = Path(__file__).with_name('reference-sources') / 'ventricle-native'
MANIFEST_SHA256 = '87b1bb7be8aed8e4d883aca8c8579f69527c6e97f3aebaa18e1549ea2942797a'
DIRECT = 'PyFLASH.markers.Antibody.find_distance_to_ventricle'
PARENT = 'PyFLASH.experiment.Experiment.addVentricleDistances'
CAPABILITY_PREFIXES = {DIRECT: ('ventricle-native.direct.',), PARENT: ('ventricle-native.parent.',)}
COMPLETE_CAPABILITIES = frozenset({DIRECT, PARENT})


def equal(actual, expected):
    """Use the boundary reference's own tolerance for all numeric geometry."""
    import numpy as np
    if isinstance(expected, dict):
        assert isinstance(actual, dict) and actual.keys() == expected.keys()
        for key in expected:
            equal(actual[key], expected[key])
    elif isinstance(expected, list):
        assert isinstance(actual, list) and len(actual) == len(expected)
        for left, right in zip(actual, expected, strict=True):
            equal(left, right)
    elif isinstance(expected, float) and math.isfinite(expected):
        assert np.isclose(actual, expected, rtol=1e-12, atol=1e-12), (actual, expected)
    else:
        assert actual == expected, (actual, expected)


def read():
    return json.loads((ARCHIVE / 'native-v1/frozen.json').read_text(encoding='utf-8'))


def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    from reproducibility import ventricle_native_reference as reference
    verify_manifest(ARCHIVE, 'source-manifest.json', MANIFEST_SHA256)
    frozen = read()
    inputs = reference.cases()
    if inputs != [row['case'] for row in frozen['rows']]:
        raise ValueError('Independent native boundary inputs changed.')
    queries = [reference.query(case) for case in inputs] + [q for case in inputs for q in reference.trace_queries(case)]
    retained = json.loads((ARCHIVE / 'native-v1/native-r/complete-ventricle-queries.json').read_text(encoding='utf-8'))
    if queries != retained:
        raise ValueError('Independent native boundary expressions changed.')
    sources = {Path(name).name: value for name, value in frozen['source_hashes'].items()}
    for path, name in ((Path(reference.__file__), 'reference.py'), (reference.ORIGINAL, 'frozen-before.json'),
                       (reference.ROOT / 'reproducibility/reference-sources/marker-calibration/native-imagej-v1/native.json', 'native.json')):
        if hashlib.sha256(path.read_bytes()).hexdigest() != sources[name]:
            raise ValueError('Independent native boundary source changed: ' + str(path))
    return frozen


def cases():
    items = []
    for row in read()['rows']:
        case = row['case']
        for implicit in (False, True):
            if implicit and 'argument_rois' in case:
                continue
            items.append({'key': 'ventricle-native.direct.' + case['key'] + '.implicit-' + str(implicit),
                          'operation': 'direct', 'implicit': implicit, 'row': row})
        for kinds in (('object',), ('cell',), ('object', 'cell')):
            for progress in (False, True):
                items.append({'key': 'ventricle-native.parent.' + case['key'] + '.' + '-'.join(kinds) + '.progress-' + str(progress),
                              'operation': 'parent', 'kinds': kinds, 'progress': progress, 'row': row})
    for progress in (False, True):
        items.append({'key': 'ventricle-native.parent.zero-markers.progress-' + str(progress),
                      'operation': 'parent', 'kinds': (), 'progress': progress, 'row': None})
    return items


def required_keys(capability):
    operation = {DIRECT: 'direct', PARENT: 'parent'}.get(capability)
    return {item['key'] for item in cases() if item['operation'] == operation}


def marker_frame(case, name):
    import pandas as pd
    frame = {field: [row.get('region') if field == 'Region' else row.get(field) for row in case['rows']]
             for field in case['marker_groups']}
    frame.update({name + '_RawXM': [row['x'] for row in case['rows']],
                  name + '_RawYM': [row['y'] for row in case['rows']],
                  name + '_ZM': [row['z'] for row in case['rows']]})
    if any('pitch' in row for row in case['rows']):
        frame[name + '_RawZM'] = frame[name + '_ZM'][:]
        frame[name + '_Count'] = [row.get('count', 1) for row in case['rows']]
        for index, field in enumerate(('Width', 'Height', 'Depth')):
            frame[name + '_SourcePixel' + field] = [row['pitch'][index] for row in case['rows']]
        frame[name + '_SourcePixelUnit'] = ['micron'] * len(case['rows'])
    result = pd.DataFrame(frame, index=case.get('index'))
    if case.get('region_index'):
        result = result.set_index('Region')
    result.attrs = {'original-row-order': 'native-ventricle-input'}
    return result


def roi_frame(case, argument=False):
    import numpy as np
    import pandas as pd
    records = case.get('argument_rois', case['rois']) if argument else case['rois']
    data = {field: [row.get('region') if field == 'Region' else row.get(field) for row in records]
            for field in case['roi_groups']}
    data.update({'x': [None if row['x'] is None else np.asarray(row['x'], dtype=float) for row in records],
                 'y': [np.asarray(row['y'], dtype=float) for row in records], 'name': [row['region'] for row in records]})
    frame = pd.DataFrame(data)
    frame.attrs = {'original-roi-order': 'native-ventricle-input'}
    return frame


def production(item, observation=None, *, experiment_class=None, marker_class=None):
    import numpy as np
    import pandas as pd
    from PyFLASH import markers
    from PyFLASH.config import Config
    from PyFLASH.experiment import Experiment
    from reproducibility.marker_nearest_contract import table, decode
    experiment = object.__new__(experiment_class or Experiment)
    experiment.name = 'native-ventricle'
    sentinel = object()
    experiment._unrelated_state = sentinel
    case = item['row']['case'] if item['row'] else None
    owned = roi_frame(case) if case else pd.DataFrame()
    argument = roi_frame(case, True) if case else pd.DataFrame()
    selected = argument if item['operation'] == 'parent' else owned
    ignored = markers.Antibody.__new__(markers.Antibody)
    ignored.name = 'ignored'
    ignored.df = pd.DataFrame({'sentinel': [71]})
    experiment.data = {'ROIs': SimpleNamespace(df=selected), 'ignored': ignored}
    kinds = item.get('kinds', ('direct',))
    aliases, originals, expected = {}, {}, {}
    for index, kind in enumerate(kinds):
        cls = {'direct': marker_class or markers.Antibody, 'object': markers.objectMarker, 'cell': markers.cellMarker}[kind]
        obj = cls.__new__(cls)
        obj.name = ('M', 'N')[index]
        obj.df = marker_frame(case, obj.name)
        obj.experiment = experiment
        obj._unrelated_state = sentinel
        experiment.data[obj.name] = obj
        aliases[obj.name] = obj.df
        originals[obj.name] = obj.df.copy(deep=True)
        answer = obj.df.copy(deep=True)
        answer[obj.name + '_DistToVentricle'] = np.asarray(decode(item['row']['expected']), dtype=float)
        expected[obj.name] = answer
    mapping = experiment.data
    original_objects = tuple(mapping.items())
    original_order = list(mapping)
    original_ignored = table(ignored.df)
    original_owned, original_argument = table(owned), table(argument)
    old_pitch = Config.PIXEL_SIZE
    try:
        if case:
            Config.PIXEL_SIZE = case['pixels_per_micron']
        with contextlib.redirect_stdout(io.StringIO()):
            if item['operation'] == 'direct':
                returned = mapping['M'].find_distance_to_ventricle(None if item['implicit'] else argument)
            else:
                returned = experiment.addVentricleDistances(progress=item['progress'])
    finally:
        Config.PIXEL_SIZE = old_pitch
    actual = {'tables': {name: table(mapping[name].df) for name in expected}, 'owned_roi': table(owned),
              'argument_roi': table(argument), 'ignored': table(ignored.df), 'return': returned,
              'data_order': list(mapping), 'retains_mapping_and_objects': experiment.data is mapping and tuple(mapping.items()) == original_objects,
              'retains_tables': all(mapping[name].df is aliases[name] for name in expected),
              'retains_unrelated_state': experiment._unrelated_state is sentinel and all(mapping[name]._unrelated_state is sentinel for name in expected)}
    answer = {'tables': {name: table(frame) for name, frame in expected.items()}, 'owned_roi': original_owned,
              'argument_roi': original_argument, 'ignored': original_ignored, 'return': None, 'data_order': original_order,
              'retains_mapping_and_objects': True, 'retains_tables': True, 'retains_unrelated_state': True}
    if item['operation'] == 'parent':
        actual['summary'] = experiment._last_ventricle_summary
        answer['summary'] = f'{len(kinds)} markers updated with ventricle distances'
    if observation is not None:
        observation.update(actual=actual, expected=answer)
    assert actual['owned_roi'] == original_owned and actual['argument_roi'] == original_argument
    assert actual['ignored'] == original_ignored
    for name, frame in expected.items():
        pd.testing.assert_frame_equal(mapping[name].df[originals[name].columns], originals[name], check_exact=True)
        pd.testing.assert_frame_equal(mapping[name].df, frame, check_exact=False, rtol=1e-12, atol=1e-12)
    equal(actual, answer)
    return actual, answer


def validate(output):
    import shapely
    from PyFLASH._persistence import write_json
    from reproducibility import ventricle_native_reference as reference
    from reproducibility.reference_runtime import execute_queries, values
    from reproducibility.normality_association_validation import comparison
    frozen = check_identity()
    output = Path(output)
    inputs = reference.cases()
    queries = [reference.query(case) for case in inputs] + [q for case in inputs for q in reference.trace_queries(case)]
    native = execute_queries(queries, output / 'native-r', name='complete-ventricle', timeout=180)
    for key, value in frozen['runtime'].items():
        if native[key] != value:
            raise ValueError('Independent native boundary runtime changed: ' + key)
    if shapely.__version__ != frozen['shapely'] or shapely.geos_version_string != frozen['geos']:
        raise ValueError('Published geometry reference runtime changed.')
    answers = {row['key']: list(values(row)) for row in native['rows']}
    for row in frozen['rows']:
        equal(reference.encode(answers[row['case']['key']]), row['expected'])
        equal(reference.geos_answer(row['case'], answers), row['geos'])
        for key, value in row['lines'].items():
            equal(answers[key], value)
    comparisons, paired = [], []
    for item in cases():
        observation, error = {}, None
        try:
            production(item, observation)
        except Exception as exc:
            error = type(exc).__name__ + ': ' + str(exc)
        actual, answer = observation.get('actual'), observation.get('expected')
        comparisons.append(comparison(item['key'], 'Native R 4.6.0 full boundary routing and published GEOS projection',
                                      'published-independent-geometry/complete-public-boundary-table-contract',
                                      actual, answer, error is None, True,
                                      'complete-original-tables-physical-distance-row-and-boundary-ownership', 1e-12, 1e-12))
        paired.append({'item': item, 'actual': actual, 'expected': answer, 'error': error})
        if error is not None:
            write_json(output / 'ventricle-native-failures.json', [row for row in paired if row['error'] is not None])
    write_json(output / 'ventricle-native-paired.json', {'rows': paired, 'scope': frozen['scope']})
    return comparisons
