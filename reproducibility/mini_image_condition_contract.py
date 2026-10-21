"""Retain acquired-image subject metadata through condition reassignment."""
from pathlib import Path
import contextlib
import hashlib
import io
import json
import shutil

ARCHIVE = Path(__file__).with_name('reference-sources') / 'mini-image-conditions-native'
MANIFEST_SHA256 = '412b1e49407cfb5859abd9b9429ea3a12f907dfea67a8792bb76019cf5860b8b'
CAPABILITY_PREFIXES = {name: ('mini-image-conditions.',) for name in (
    'PyFLASH.experiment.MiniExperiment.set_condition_list',
    'PyFLASH.experiment.MiniExperiment.processData',
    'PyFLASH.experiment.Experiment.importImages',
    'PyFLASH.experiment.Experiment.getImageTable')}
COMPLETE_CAPABILITIES = frozenset()


def read(name):
    return json.loads((ARCHIVE / name).read_text(encoding='utf-8'))


def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    verify_manifest(ARCHIVE, 'source-files.json', MANIFEST_SHA256)


def cases():
    return [dict(key='mini-image-conditions.' + str(row['progress']), **row)
            for row in read('original/before.json')['rows']]


def production(item, output, observation=None):
    import pandas as pd
    from PyFLASH.experiment import MiniExperiment
    from PyFLASH.conditions import condition, conditionList
    from reproducibility.scientific_utility_contract import table
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    original = ARCHIVE / 'original' / str(item['progress'])
    shutil.copyfile(original / 'Data.csv', output / 'Data.csv')
    expected = json.loads(json.dumps(item['expected']))
    position = expected['columns'].index('ImagePath')
    inputs = {'Data.csv': hashlib.sha256((output / 'Data.csv').read_bytes()).hexdigest()}
    for row in expected['rows']:
        source_path = Path(row[position])
        relative = source_path.relative_to(source_path.parents[2])
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original / relative, destination)
        inputs[relative.as_posix()] = hashlib.sha256(destination.read_bytes()).hexdigest()
        row[position] = str(destination)
    experiment = MiniExperiment('Acquired-image subject metadata', str(output))
    conditions = conditionList([condition('Control', 'Control', None, 'Treatment'),
                                condition('Treated', 'Treated', None, 'Treatment')])
    with contextlib.redirect_stdout(io.StringIO()):
        experiment.processData(import_images=True, progress=item['progress'])
        experiment.set_condition_list(conditions)
    # Check stored metadata before a getter can refresh it and hide stale state.
    actual = table(experiment.images)
    if observation is not None:
        observation.update(actual=actual, expected=expected)
    assert actual == expected
    full = experiment.getImageTable(include_summary=True)
    assert full is not experiment.images and table(full) == expected
    base = experiment.getImageTable(include_summary=False)
    pd.testing.assert_frame_equal(base, full[expected['columns'][:6]])
    assert base is not experiment.images
    lookup = {animal: {'M': {'LHSCN': str(output / 'Images' / animal / 'M_LHSCN.png')}}
              for animal in ('A1', 'B2')}
    assert experiment.imagesDict == lookup
    assert all(hashlib.sha256((output / name).read_bytes()).hexdigest() == sha for name, sha in inputs.items())
    return actual, expected


def validate(output):
    from reproducibility.reference_runtime import execute_queries
    check_identity()
    original = read('original/native/acquired-image-conditions-queries.json')
    native = execute_queries(original, Path(output) / 'native', name='acquired-image-conditions')
    assert native['rows'] == read('original/native/acquired-image-conditions-results.json')['rows']
    from reproducibility.table_family_validation import replay
    return replay(cases(), lambda item, observed, path: production(item, path, observed), output,
        reference='Original native R full subject/image metadata merge',
        family='native-image-metadata/full-condition-refresh',
        shape='every-image-field-copy-option-ownership-and-original-pixel')
