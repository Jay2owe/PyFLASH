"""Literal ownership contract for the public marker table setter, no math vote."""
from pathlib import Path
from itertools import product
import json, hashlib, copy
import numpy as np
import pandas as pd

OWNER = Path(__file__).with_name('marker-assignment-functional-20261008-v1')
KINDS = ('none', 'integer', 'float', 'text', 'list', 'tuple', 'dictionary',
         'array', 'empty-frame', 'frame', 'duplicate-frame', 'nullable-frame')
EXPECTED = dict(returned_input=True, stored_input=True, supplied_unchanged=True,
                old_value_unchanged=True, unrelated_state_retained=True,
                later_input_edit_visible=True)


def cases():
    return [dict(key='.'.join((owner, kind, old)), owner=owner, kind=kind, old=old)
            for owner, kind, old in product(('Antibody', 'objectMarker', 'cellMarker'), KINDS, ('none', 'frame'))]


def supplied(kind):
    if kind == 'none': return None
    if kind == 'integer': return 2**100 + 1
    if kind == 'float': return float('-inf')
    if kind == 'text': return 'literal table owner'
    if kind == 'list': return [1, None, {'native': 3}]
    if kind == 'tuple': return ('a', None, 7)
    if kind == 'dictionary': return {'a': [1, 2], 'b': None}
    if kind == 'array': return np.array([[1., np.nan], [np.inf, -0.]])
    if kind == 'empty-frame': return pd.DataFrame(columns=['AnimalName', 'Value'])
    if kind == 'nullable-frame':
        frame = pd.DataFrame({'AnimalName': pd.Series(['001', None], dtype='string'),
                              'Value': pd.Series([2**62+1, None], dtype='Int64')})
    elif kind == 'duplicate-frame':
        frame = pd.DataFrame([[1., 2.], [3., 4.]], columns=['Value', 'Value'], index=[9, 9])
    else:
        frame = pd.DataFrame({'AnimalName': ['WT1', 'KO2'], 'Value': [1.25, -0.]},
                             index=pd.Index([9, 2], name='original'))
    frame.attrs['original'] = {'values': [1, 2]}
    return frame


def unchanged(actual, original):
    if isinstance(actual, pd.DataFrame):
        pd.testing.assert_frame_equal(actual, original, check_exact=True)
        assert actual.attrs == original.attrs
    elif isinstance(actual, np.ndarray):
        np.testing.assert_array_equal(actual, original)
    else:
        assert actual == original


def production(case):
    from PyFLASH import markers
    marker = object.__new__(getattr(markers, case['owner']))
    old = None if case['old'] == 'none' else supplied('frame')
    marker.df = old
    experiment = object()
    marker.experiment = experiment
    marker.name = 'Original marker'
    marker.threshold = 1.5
    marker._assignment_unrelated = {'original': [1, 2]}
    state = dict(marker.__dict__)
    original_old = copy.deepcopy(old)
    value = supplied(case['kind'])
    original = copy.deepcopy(value)
    result = marker.set_df(value)
    assert result is value and marker.df is value
    unchanged(value, original)
    unchanged(old, original_old)
    assert marker.__dict__.keys() == state.keys()
    assert all(marker.__dict__[key] is identity for key, identity in state.items() if key != 'df')
    if isinstance(value, pd.DataFrame):
        value.attrs['later'] = [3]
        assert result.attrs['later'] == marker.df.attrs['later'] == [3]
    elif isinstance(value, np.ndarray):
        value[0, 0] = 19.
        assert result[0, 0] == marker.df[0, 0] == 19.
    elif isinstance(value, list):
        value.append('later')
        assert result[-1] == marker.df[-1] == 'later'
    elif isinstance(value, dict):
        value['later'] = 19
        assert result['later'] == marker.df['later'] == 19
    return dict(EXPECTED)


def freeze():
    from PyFLASH import markers
    source = Path(markers.__file__)
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    before = digest(source)
    OWNER.mkdir(exist_ok=False)
    rows = []
    for case in cases():
        try:
            actual = production(case)
            passed, error = actual == EXPECTED, None
        except Exception as exc:
            actual, passed, error = None, False, type(exc).__name__ + ': ' + str(exc)
        rows.append(dict(case=case, expected=EXPECTED, actual=actual, passed=passed, error=error))
    assert digest(source) == before
    record = dict(actual_calls=len(rows), failed=sum(not row['passed'] for row in rows),
                  source_unchanged=True, source_sha256=before, rows=rows,
                  scope='Complete direct one-argument assignment and identity contract across supported subclasses and mutable/immutable carriers. Functional ownership only, no scientific calculation or downstream method vote.')
    (OWNER / 'before.json').write_text(json.dumps(record, indent=2) + '\n')
    (OWNER / 'original-markers.py').write_bytes(source.read_bytes())
    (OWNER / 'original-reference.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps({key: record[key] for key in ('actual_calls', 'failed', 'source_unchanged')}), flush=True)


if __name__ == '__main__':
    freeze()
