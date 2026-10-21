"""Original native-R exclusion and metadata controls, frozen before correction.

This verification producer compares entire public summary tables and ownership.
It does not reuse package numeric conversion, grouping or summary code for answers.
"""
from pathlib import Path
import contextlib, io, json, hashlib, math
import pandas as pd
from statistics import mean
from reproducibility.reference_runtime import execute_queries, values
from reproducibility.scientific_utility_contract import table

SENTINEL = 'NOT_INCLUDED_IN_EXPERIMENT'
OWNER = Path(__file__).resolve().parent

def cases():
    samples = {
        'middle': [1, SENTINEL, 3], 'first': [SENTINEL, 1, 3],
        'last': [1, 3, SENTINEL], 'numeric-text': ['1', SENTINEL, '3'],
        'missing': [1, None, SENTINEL, 3], 'excluded': [SENTINEL, SENTINEL],
        'unmeasured': [None, None], 'prefixed': [1, 'reason:' + SENTINEL, 3],
        'negative': [-3, SENTINEL, -1], 'zero': [0, SENTINEL, 0],
        'tiny': [1e-300, SENTINEL, 3e-300], 'plain-text': ['1', '2', '3'],
    }
    for key, sample in samples.items():
        for metadata in ('object', 'string', 'category', 'datetime'):
            for progress in (False, True):
                yield {'key': key + '.' + metadata + '.' + str(progress),
                       'sample': sample, 'metadata': metadata, 'progress': progress,
                       'numeric': key != 'plain-text'}

def frame(case):
    n = len(case['sample'])
    # Numeric-looking factor labels are identifiers, even beside exclusions.
    data = pd.DataFrame({'AnimalName': ['A1'] * n + ['B2'] * n,
        'Value': pd.Series(case['sample'] + [3, SENTINEL][:n] + [None] * max(0, n-2), dtype=object),
        'Treatment': ['001', SENTINEL][:n] + ['001'] * max(0, n-2)
                     + ['002'] * n})
    if not case['numeric']:
        data['Value'] = pd.Series(case['sample'] + ['4'] * n, dtype=object)
    raw = ['alpha', None][:n] + ['omega'] * max(0, n-2) + ['beta'] * n
    if case['metadata'] == 'datetime':
        data['Label'] = pd.to_datetime(['2020-01-01', None][:n] + ['2020-02-01'] * max(0,n-2)
                                      + ['2021-01-01'] * n)
    else:
        data['Label'] = pd.Series(raw, dtype=case['metadata'])
    return data

def query(case):
    data = frame(case)
    parts = []
    for animal in ('A1', 'B2'):
        sample = data.loc[data.AnimalName == animal, 'Value'].tolist()
        if not case['numeric']:
            parts.append(json.dumps(next(v for v in sample if v is not None)))
        else:
            kept = [float(v) for v in sample if v is not None and SENTINEL not in str(v)]
            excluded = any(SENTINEL in str(v) for v in sample)
            parts.append('"' + SENTINEL + '"' if not kept and excluded else
                         'NA_real_' if not kept else 'as.character(mean(c(' + ','.join(map(repr, kept)) + ')))')
    return {'key': case['key'], 'code': 'c(' + ','.join(parts) + ')'}

def expected(case, answer):
    data = frame(case)
    result = pd.DataFrame({'AnimalName': ['A1', 'B2']})
    if case['numeric']:
        numeric = [math.nan if v is None else SENTINEL if v == SENTINEL else float(v) for v in answer]
        for animal, value in zip(('A1','B2'), numeric):
            kept = [float(v) for v in data.loc[data.AnimalName == animal,'Value']
                    if v is not None and SENTINEL not in str(v)]
            if kept:
                assert math.isclose(value, mean(kept), rel_tol=1e-14, abs_tol=0)
        result['Value'] = numeric
    else:
        result['Value'] = answer
    result['Treatment'] = ['001','002']
    if case['metadata'] == 'datetime':
        result['Label'] = pd.to_datetime(['2020-01-01','2021-01-01'])
    else:
        result['Label'] = pd.Series(['alpha','beta'],dtype=case['metadata'])
        if case['metadata']=='category':
            result['Label'] = result['Label'].cat.set_categories(data.Label.cat.categories)
    result['Condition'] = ['A','B']
    return result

def encoded(data):
    def transport(value):
        if value is pd.NA or value is pd.NaT: return None
        if isinstance(value, pd.Timestamp): return value.isoformat()
        raise TypeError(type(value).__name__)
    return json.loads(json.dumps(table(data), default=transport))

def production(case, expected_frame):
    from PyFLASH.experiment import MiniExperiment
    from PyFLASH.markers import Attribute
    experiment = MiniExperiment('Original exclusions and metadata', str(OWNER),
                                factor_mappings={'Treatment': {'001': 'control', '002': 'treated'}})
    data = frame(case)
    carrier = Attribute('Measurements', data, experiment)
    experiment.data = {'Measurements': carrier}
    original = encoded(carrier.df)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            result = experiment.createSummary(progress=case['progress'])
        actual = encoded(result)
        pd.testing.assert_frame_equal(result, expected_frame, check_exact=False, rtol=1e-14, atol=0)
        assert result is experiment.summary and result is experiment.summaries['SCN']
        assert experiment.data['Measurements'] is carrier and carrier.df is data
        assert encoded(data) == original
        return {'passed': True, 'actual': actual, 'input': original}
    except Exception as error:
        return {'passed': False, 'actual': encoded(experiment.summary) if hasattr(experiment,'summary') else None,
                'error': type(error).__name__ + ': ' + str(error), 'input': original}

def freeze():
    output = OWNER / 'exclusions-original'
    assert not output.exists()
    output.mkdir()
    import PyFLASH.experiment as module
    source = Path(module.__file__)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    items = list(cases())
    native = execute_queries([query(case) for case in items], output/'native',name='excluded-measurement-means')
    rows = []
    for case, native_row in zip(items, native['rows'], strict=True):
        answer = values(native_row)
        expect = expected(case, answer)
        rows.append({'case':case,'native':native_row,'expected':encoded(expect), **production(case,expect)})
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    record = {'source_sha256':before,'source_unchanged':True,'actual_calls':len(rows),
              'failed':sum(not r['passed'] for r in rows),'rows':rows,
              'scope':'Excluded observation means and protected typed metadata only; whole summary remains partial.'}
    (output/'before.json').write_text(json.dumps(record,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    (output/'original-experiment.py').write_bytes(source.read_bytes())
    (output/'original-reference.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps({k:record[k] for k in ('actual_calls','failed','source_unchanged')}),flush=True)

if __name__ == '__main__': freeze()
