"""Retain literal display labels, whole tables and ownership for the public getter.

All expected labels and ROI selection choices below are audit-authored functional
requirements, not outputs copied from the label formatter. No scientific value
is calculated or independently certified by this presentation-only contract.
Output is new-only JSON with original input/code identities and every failed call.
"""
from pathlib import Path
from itertools import product
import argparse, copy, hashlib, json, shutil
import numpy as np
import pandas as pd

# Configuration: literal labels deliberately cover every formatter route.
COLUMNS = ['AnimalName', 'Condition', 'M_CountRaw', 'ROI_Thickness', 'ROI_Volume',
    'ROI_Area', 'M_VolumeMean', 'Period', 'Totalcounts', 'custom_measurement',
    'camelCaseMeasurement', 17]
LABELS = ['Animal Name', 'Condition', 'M Raw Count', 'ROI Thickness (µm)',
    'ROI Volume (µm³)', 'ROI Area (µm²)', 'M Mean Volume (µm³)',
    'Circadian period (hours)', 'Total counts', 'custom measurement',
    'camel Case Measurement', '17']

def frame(kind, offset=0):
    result = pd.DataFrame({name: [2**100 + 1 + offset, 2**100 + 3 + offset, None]
        for name in COLUMNS}, dtype=object, index=pd.Index([9, 2, 9], name='literal'))
    result['AnimalName'] = pd.array(['001', 'NA', '003'], dtype='string')
    result['Condition'] = pd.array(['WT', None, 'KO'], dtype='string')
    result['M_CountRaw'] = pd.array([1 + offset, None, 3 + offset], dtype='Int64')
    result['ROI_Thickness'] = [1.25 + offset, np.nan, np.inf]
    result.attrs = {'origin': ['literal', 'preserved'], 'unit': 'declared'}
    if kind == 'empty': result = result.iloc[:0].copy()
    elif kind == 'duplicate-labels':
        result = pd.concat([result, result[['M_CountRaw']]], axis=1)
    elif kind == 'column-index-name': result.columns.name = 'original columns'
    return result

def cases():
    owners = ('Experiment', 'MiniExperiment', 'Batch')
    queries = (None, 'SCN', 'OC', 'missing')
    result = [dict(key='.'.join(map(str, (owner, mode, kind, query))), owner=owner,
        mode=mode, kind=kind, query=query)
        for owner, mode, kind, query in product(owners,
            ('both', 'only-other', 'empty-mapping', 'absent-mapping'),
            ('ordinary', 'empty', 'duplicate-labels', 'column-index-name'), queries)]
    result.extend(dict(key='.'.join(map(str, (owner, 'nonframe', kind, query))),
        owner=owner, mode='nonframe', kind=kind, query=query)
        for owner, kind, query in product(owners, ('none', 'integer', 'text', 'list'), queries))
    return result

def production(case):
    from PyFLASH.experiment import Experiment, MiniExperiment
    from PyFLASH.batch import Batch
    from reproducibility.scientific_utility_contract import table as base_table
    def table(value):
        result = base_table(value)
        result['rows'] = [['NaN' if entry is pd.NA else entry for entry in row]
            for row in result['rows']]
        return result
    cls = {'Experiment': Experiment, 'MiniExperiment': MiniExperiment, 'Batch': Batch}[case['owner']]
    obj = object.__new__(cls)
    unrelated = object(); obj._unrelated_state = unrelated
    mapping = None
    if case['mode'] == 'nonframe':
        source = {'none': None, 'integer': 7, 'text': 'unchanged', 'list': ['original']}[case['kind']]
        obj.summaries = {'SCN': source}
        expected = source
    elif case['mode'] == 'both':
        obj.summaries = {'SCN': frame(case['kind']), 'OC': frame(case['kind'], 10)}
        source = obj.summaries['OC' if case['query'] == 'OC' else 'SCN']
    elif case['mode'] == 'only-other':
        obj.summaries = {'OC': frame(case['kind'], 10)}
        source = obj.summaries['OC']
    else:
        if case['mode'] == 'empty-mapping': obj.summaries = {}
        source = pd.DataFrame(columns=['AnimalName'])
    if hasattr(obj, 'summaries'): mapping = obj.summaries
    original = dict(obj.__dict__)
    snapshots = {key: value.copy(deep=True) if isinstance(value, pd.DataFrame) else copy.deepcopy(value)
        for key, value in (mapping or {}).items()}
    if isinstance(source, pd.DataFrame):
        expected = source.copy(deep=True)
        known = dict(zip(COLUMNS, LABELS))
        expected.columns = [known[column] for column in source.columns]
    try:
        actual = obj.getDisplaySummary(case['query'])
        assert obj.__dict__.keys() == original.keys()
        assert all(obj.__dict__[key] is value for key, value in original.items())
        assert obj._unrelated_state is unrelated
        for key, snapshot in snapshots.items():
            if isinstance(snapshot, pd.DataFrame):
                pd.testing.assert_frame_equal(mapping[key], snapshot, check_exact=True)
            else: assert mapping[key] == snapshot
        if isinstance(expected, pd.DataFrame):
            pd.testing.assert_frame_equal(actual, expected, check_exact=True)
            assert actual is not source
            observed = table(actual)
            predicted = table(expected)
            # Editing a returned scalar must never mutate caller measurements.
            if not actual.empty:
                actual.iloc[0, 0] = 'edited display'
                assert source.iloc[0, 0] == '001'
        else:
            assert actual is source
            observed = predicted = actual
        return dict(passed=True, actual=observed, expected=predicted)
    except Exception as error:
        return dict(passed=False, error=type(error).__name__ + ': ' + str(error))

def freeze(output):
    from PyFLASH import experiment, batch, export
    paths = [Path(__file__), Path(experiment.__file__), Path(batch.__file__), Path(export.__file__)]
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    hashes = {str(path): digest(path) for path in paths}
    assert not output.exists() and shutil.disk_usage(output.parent).free >= 100 * 1024**2
    output.mkdir(); (output / 'rows').mkdir()
    items = cases()
    (output / 'inputs.json').write_text(json.dumps(dict(columns=COLUMNS, labels=LABELS, cases=items), indent=2) + '\n')
    rows = []
    for case in items:
        row = dict(case=case, **production(case)); rows.append(row)
        (output / 'rows' / (case['key'] + '.json')).write_text(json.dumps(row, indent=2, allow_nan=False) + '\n')
    changes = [str(path) for path in paths if digest(path) != hashes[str(path)]]
    assert not changes, changes
    for index, path in enumerate(paths): (output / ('original-' + str(index) + '-' + path.name)).write_bytes(path.read_bytes())
    record = dict(actual_calls=len(rows), failed=sum(not row['passed'] for row in rows),
        source_hashes=hashes, source_changes=changes, rows=rows,
        scope='Complete declared ROI-selection, whole-table display and copy ownership branches. Literal functional presentation requirements; no independent numerical science vote.')
    (output / 'before.json').write_text(json.dumps(record, indent=2, allow_nan=False) + '\n')
    print(json.dumps({key: record[key] for key in ('actual_calls', 'failed', 'source_changes')}), flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); freeze(args.output)
