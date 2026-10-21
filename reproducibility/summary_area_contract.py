"""Full native area-normalization tables; other summary branches remain open."""
from pathlib import Path
import contextlib
import hashlib
import io
import json

ARCHIVE = Path(__file__).with_name('reference-sources') / 'summary-area-native'
MANIFEST_SHA256 = '3edab457962106ed393e9e9e2c2957ed31f5e21c0a059efe9df582a25b8577f2'
CAPABILITY_PREFIXES = {'PyFLASH.experiment.Experiment.createSummary': ('summary-area-native.',)}
COMPLETE_CAPABILITIES = frozenset()


def read():
    return json.loads((ARCHIVE / 'native-r/frozen.json').read_text())


def reference_module():
    from reproducibility import summary_area_reference as reference
    reference.NATIVE = ARCHIVE / 'native-imagej-v1/receipt.json'
    return reference


def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    verify_manifest(ARCHIVE, 'source-manifest.json', MANIFEST_SHA256)
    frozen = read()
    reference = reference_module()
    if reference.cases() != [row['case'] for row in frozen['rows']]:
        raise ValueError('Native area summary inputs changed.')
    queries = json.loads((ARCHIVE / 'native-r/summary-area-full-tables-queries.json').read_text())
    if queries != [reference.query(case) for case in reference.cases()]:
        raise ValueError('Independent area summary equations changed.')
    sources = {Path(name).name: sha for name, sha in frozen['sources'].items()}
    for path, name in ((Path(reference.__file__), 'reference.py'),
                       (ARCHIVE / 'native-imagej-v1/receipt.json', 'receipt.json'),
                       (ARCHIVE / 'native-imagej-v1/NativeArea.java', 'NativeArea.java'),
                       (ARCHIVE / 'native-imagej-v1/AI_Exports/native.json', 'native.json')):
        if hashlib.sha256(path.read_bytes()).hexdigest() != sources[name]:
            raise ValueError('Original native area source changed: ' + str(path))
    return frozen


def cases():
    return [{'key': 'summary-area-native.' + row['case']['key'], 'case': row['case'], 'expected': row['expected']}
            for row in read()['rows']]


def production(item, observation=None, reference=None):
    import pandas as pd
    from PyFLASH.experiment import Experiment
    from PyFLASH.markers import objectMarker
    from PyFLASH.dataframe import DataFrameTable
    from PyFLASH.config import Config
    from reproducibility.marker_nearest_contract import table
    from reproducibility.ventricle_native_contract import equal
    reference = reference or reference_module()
    case = item['case']
    measured, sections, thickness = case['native'], case['sections'], case['thickness']
    experiment = Experiment.__new__(Experiment)
    experiment.name = 'native-area'
    marker = objectMarker.__new__(objectMarker)
    marker.name = 'M'
    marker.df = pd.DataFrame({'AnimalName': ['Subject1'] * (2 * sections), 'ROI': ['SCN'] * (2 * sections),
        'Region': ['SCN' + str(index + 1) for index in range(sections) for _ in range(2)],
        'M_Count': [1] * (2 * sections)})
    area = measured['pixel_area'] if case['area_column'] == 'Area(pixel)' else measured['physical_area']
    props = pd.DataFrame({'AnimalName': ['Subject1'] * sections, 'ROI': ['SCN'] * sections,
        'Region': ['SCN' + str(index + 1) for index in range(sections)], case['area_column']: [area] * sections})
    if case['volume_column']:
        volume = measured['physical_area'] * thickness
        props[case['volume_column']] = volume / 1e9 if case['volume_column'] == 'Volume(mm^3)' else volume
    experiment.data = {'M': marker, 'ROI Properties': DataFrameTable('ROI Properties', props)}
    mapping = experiment.data
    objects = tuple(mapping.items())
    aliases = {name: obj.df for name, obj in mapping.items()}
    originals = {name: obj.df.copy(deep=True) for name, obj in mapping.items()}
    old_density, old_thickness = Config.PIXEL_SIZE, Config.SECTION_THICKNESS_UM
    try:
        Config.PIXEL_SIZE, Config.SECTION_THICKNESS_UM = measured['density'], thickness
        with contextlib.redirect_stdout(io.StringIO()):
            returned = experiment.createSummary(progress=case['progress'])
    finally:
        Config.PIXEL_SIZE, Config.SECTION_THICKNESS_UM = old_density, old_thickness
    expected = reference.expected(case, item['expected'])
    actual = {'summary': table(returned['SCN']), 'roi_keys': list(returned), 'return_alias': returned is experiment.summaries,
              'original_tables': {name: table(obj.df) for name, obj in mapping.items()},
              'retains_mapping': experiment.data is mapping and tuple(mapping.items()) == objects,
              'retains_table_aliases': all(obj.df is aliases[name] for name, obj in mapping.items()),
              'summary_text': experiment._last_summary_summary}
    answer = {'summary': table(expected), 'roi_keys': ['SCN'], 'return_alias': True,
              'original_tables': {name: table(frame) for name, frame in originals.items()},
              'retains_mapping': True, 'retains_table_aliases': True,
              'summary_text': f'1 ROI(s) | 1 subjects x {expected.shape[1]} total columns'}
    if observation is not None:
        observation.update(actual=actual, expected=answer)
    for name, obj in mapping.items():
        pd.testing.assert_frame_equal(obj.df, originals[name], check_exact=True)
    pd.testing.assert_frame_equal(returned['SCN'], expected, check_exact=False, rtol=1e-12, atol=0.)
    equal(actual, answer)
    return actual, answer


def validate(output):
    from PyFLASH._persistence import write_json
    from reproducibility.normality_association_validation import comparison
    from reproducibility.reference_runtime import execute_queries, values
    from reproducibility.ventricle_native_contract import equal
    frozen = check_identity()
    reference = reference_module()
    output = Path(output)
    native = execute_queries([reference.query(case) for case in reference.cases()], output / 'native-r',
                             name='summary-area-full-tables', timeout=180)
    for key, value in frozen['runtime'].items():
        if native[key] != value:
            raise ValueError('Native area summary runtime changed: ' + key)
    for original, row in zip(frozen['rows'], native['rows'], strict=True):
        equal(list(values(row)), original['expected'])
    rows, paired = [], []
    for item in cases():
        observation, error = {}, None
        try:
            production(item, observation)
        except Exception as exc:
            error = type(exc).__name__ + ': ' + str(exc)
        actual, answer = observation.get('actual'), observation.get('expected')
        rows.append(comparison(item['key'], 'Original ImageJ 1.54p calibrated area and native R count/volume normalization',
                    'published-calibration/independent-full-area-summary-contract', actual, answer, error is None, True,
                    'every-summary-column-and-input-table-across-pixel-micron-and-explicit-volume-routes', 1e-12, 0.))
        paired.append({'item': item, 'actual': actual, 'expected': answer, 'error': error})
        if error:
            write_json(output / 'summary-area-failures.json', [row for row in paired if row['error']])
    write_json(output / 'summary-area-paired.json', {'rows': paired, 'scope': frozen['scope']})
    return rows
