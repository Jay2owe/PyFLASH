"""Capture whole image-table getters against literal/SQLite metadata ownership.

Authored image paths are indexed metadata; no pixels are decoded or figures
drawn. Persist all table fields, storage, indexes, attributes, return copies,
refresh state and unrelated/nested caller ownership before any repair.
"""
from pathlib import Path
from itertools import product
import argparse, contextlib, copy, hashlib, io, json, shutil, sqlite3, sys
import numpy as np
import pandas as pd
from reproducibility.whole_condition_reference import table

# Configuration: complete public switches and declared table/lifecycle profiles.
PROFILES = ('absent', 'empty', 'no-subject', 'no-condition', 'object', 'string',
            'indexed', 'multi-index', 'duplicate', 'experiment-key')
BASE_COLUMNS = ['Experiment', 'AnimalName', 'Marker', 'ROI', 'ImageName', 'ImagePath', 'Extension']


def cases():
    for owner, profile, image_state, option in product(('Experiment', 'MiniExperiment', 'Batch'),
            PROFILES, ('cached', 'empty', 'missing', 'invalid'), (False, True, 'default')):
        yield dict(key='.'.join(map(str, (owner, profile, image_state, option))), owner=owner,
                   profile=profile, image_state=image_state, option=option)


def summary(case):
    profile = case['profile']
    if profile == 'absent':
        return None
    frame = pd.DataFrame({'AnimalName': ['A1', 'B2', 'A1'], 'Measurement': [1.25, 2.5, 3.75],
                          'Condition': ['G1', 'G2', 'later'], 'Treatment': ['T', 'C', 'later']})
    frame.attrs = {'units': {'measurement': 'acquired'}, 'preserved': [1, 2]}
    if profile == 'empty':
        frame = frame.iloc[:0].copy()
    elif profile == 'no-subject':
        frame = frame.drop(columns='AnimalName')
    elif profile == 'no-condition':
        frame = frame.drop(columns='Condition')
    elif profile == 'string':
        for name in ('AnimalName', 'Condition', 'Treatment'):
            frame[name] = frame[name].astype('string')
    elif profile == 'indexed':
        frame = frame.set_index('AnimalName')
    elif profile == 'multi-index':
        frame['Occurrence'] = [9, 3, 11]
        frame = frame.set_index(['AnimalName', 'Occurrence'])
    elif profile == 'experiment-key':
        frame['AnimalName'] = ['A1', 'A1', 'A1']
        frame['Experiment'] = ['E1', 'E2', 'E1']
    return frame


def images(case):
    if case['image_state'] in ('missing', 'invalid'):
        return None
    frame = pd.DataFrame({'Experiment': ['E1', 'E2', 'E1'], 'AnimalName': ['A1', 'B2', 'Missing'],
        'Marker': ['M', 'N', 'M'], 'ROI': ['LHSCN', 'RHSCN2', 'OC'],
        'ImageName': ['M_LHSCN', 'N_RHSCN2', 'M_OC'],
        'ImagePath': ['literal/first.png', 'literal/second.tif', 'literal/third.jpg'],
        'Extension': ['.png', '.tif', '.jpg'], 'Condition': ['stale'] * 3,
        'Treatment': ['stale'] * 3, 'AcquiredNumber': [17, 31, 47]})
    if case['profile'] == 'experiment-key':
        frame['AnimalName'] = ['A1', 'A1', 'Missing']
    frame.index = pd.Index([17, 11, 3], name='acquired-order')
    frame.attrs = {'image_metadata': {'acquisition': 'literal', 'units': 'pixels'}, 'retained': [3, 1]}
    return frame.iloc[:0].copy() if case['image_state'] == 'empty' else frame


def expected(case):
    image = images(case)
    if image is None:
        return pd.DataFrame(columns=BASE_COLUMNS[1:])
    if case['option'] is False:
        return image[BASE_COLUMNS].copy()
    source = summary(case)
    if image.empty or source is None or source.empty:
        return image.copy()
    if 'AnimalName' not in source.columns:
        if 'AnimalName' not in source.index.names:
            return image.copy()
        source = source.reset_index(level='AnimalName')
    columns = [name for name in ('Condition', 'Treatment') if name in source.columns]
    if not columns:
        return image.copy()
    keys = ['Experiment', 'AnimalName'] if 'Experiment' in source.columns and 'Experiment' in image.columns else ['AnimalName']
    # SQLite is a separate relational implementation. Ordered lookup preserves
    # the first owned row, including duplicated subjects and experiment keys.
    with sqlite3.connect(':memory:') as database:
        source[keys + columns].to_sql('metadata', database, index=False)
        values = []
        query = 'SELECT ' + ','.join('"' + name + '"' for name in columns) + ' FROM metadata WHERE ' + ' AND '.join('"' + name + '" = ?' for name in keys) + ' ORDER BY rowid LIMIT 1'
        for _, row in image.iterrows():
            result = database.execute(query, tuple(row[name] for name in keys)).fetchone()
            values.append(result or tuple(None for _ in columns))
    out = image.drop(columns=[name for name in columns if name in image]).reset_index(drop=True)
    for index, name in enumerate(columns):
        dtype = source[name].dtype
        missing = pd.NA if isinstance(dtype, pd.StringDtype) else np.nan
        out[name] = pd.Series([missing if row[index] is None else row[index] for row in values], dtype=dtype)
    out.attrs = copy.deepcopy(image.attrs)
    return out


def production(case, directory):
    from PyFLASH.experiment import Experiment, MiniExperiment
    from PyFLASH.batch import Batch
    cls = {'Experiment': Experiment, 'MiniExperiment': MiniExperiment, 'Batch': Batch}[case['owner']]
    obj = object.__new__(cls)
    obj.name = 'Image table ownership'
    obj.filePath = str(directory / 'uncreated/Data Analysis')
    obj.source_root = str(directory / 'uncreated')
    obj.data = {}
    obj.markers = set()
    obj.factor = ['Treatment']
    obj.imagesDict = {'retained': {'paths': ['literal']}}
    obj._image_unrelated = object()
    if cls is Batch:
        obj.experiment_list = []
    supplied = summary(case)
    obj.summaries = {} if supplied is None else {'SCN': supplied}
    cached = images(case)
    if case['image_state'] == 'invalid':
        obj.images = ['invalid cached image table']
    elif case['image_state'] != 'missing':
        obj.images = cached
    original_summary = None if supplied is None else supplied.copy(deep=True)
    original_images = None if cached is None else cached.copy(deep=True)
    nested = copy.deepcopy(obj.imagesDict)
    unrelated = obj._image_unrelated
    target = expected(case)
    result = None
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            result = obj.getImageTable() if case['option'] == 'default' else obj.getImageTable(include_summary=case['option'])
        assert result is not getattr(obj, 'images', None)
        pd.testing.assert_frame_equal(result, target, check_exact=True)
        assert result.attrs == target.attrs
        if supplied is not None:
            pd.testing.assert_frame_equal(supplied, original_summary, check_exact=True)
            assert supplied.attrs == original_summary.attrs and obj.summaries['SCN'] is supplied
        if cached is not None:
            pd.testing.assert_frame_equal(cached, original_images, check_exact=True)
            assert cached.attrs == original_images.attrs and obj.imagesDict == nested
            assert (obj.images is cached) == (case['option'] is False or cached.empty)
        else:
            assert obj.images.empty and obj.imagesDict == {}
        assert obj._image_unrelated is unrelated
        actual = table(result)
        if len(result):
            column = result.columns.get_loc('Marker')
            result.iloc[0, column] = 'caller-only-edit'
            assert getattr(obj, 'images').iloc[0, getattr(obj, 'images').columns.get_loc('Marker')] != 'caller-only-edit'
        return dict(passed=True, actual=actual, expected=table(target), ownership_preserved=True)
    except Exception as error:
        return dict(passed=False, actual=None if result is None else table(result), expected=table(target),
                    error=type(error).__name__ + ': ' + str(error))


def freeze(output):
    import PyFLASH.experiment as experiment
    import PyFLASH.batch as batch
    assert not output.exists()
    assert shutil.disk_usage(output.parent).free >= 64 * 1024**2
    output.mkdir()
    paths = [Path(experiment.__file__), Path(batch.__file__), Path(__file__)]
    sources = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    for index, path in enumerate(paths):
        shutil.copyfile(path, output / ('original-' + str(index) + '-' + path.name))
    items = list(cases())
    (output / 'inputs.json').write_text(json.dumps(items, indent=2) + '\n', encoding='utf-8')
    for case in items:
        json.dumps(table(expected(case)), allow_nan=False)
    rows = [dict(case=case, **production(case, output / 'cases' / case['key'])) for case in items]
    changes = [name for name, sha in sources.items() if hashlib.sha256(Path(name).read_bytes()).hexdigest() != sha]
    record = {'status': 'finished', 'actual_calls': len(rows), 'failed': sum(not row['passed'] for row in rows),
              'rows': rows, 'sources': sources, 'source_changes': changes,
              'sqlite': sqlite3.sqlite_version, 'python': sys.version,
              'scope': 'Whole functional image-table retrieval and refresh on the declared profiles; literal acquired table fields and SQLite first-owned metadata rows; no pixel decoding or additional scientific-method vote.'}
    (output / 'before.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: record[key] for key in ('actual_calls', 'failed', 'source_changes')}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    freeze(parser.parse_args().output)
