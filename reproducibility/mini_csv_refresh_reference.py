"""Freeze native CSV fields and atomic refresh ownership before correction."""
from pathlib import Path
from itertools import product
import json, contextlib, io, hashlib
import pandas as pd
from reproducibility.reference_runtime import execute_queries, values
from reproducibility.scientific_utility_contract import table

OWNER = Path(__file__).resolve().parent
INITIAL = {'Data.csv': 'ID,Value\nA01,1.25\nB02,3.75\n',
           'Removed.csv': 'ID,Value\nA01,5.25\nB02,7.75\n'}


def cases():
    for mode, labels, progress in product(('replace', 'add', 'remove', 'rename', 'empty',
                                          'invalid-last', 'invalid-first', 'header-only'),
                                         (False, True), (False, True)):
        yield dict(key='.'.join(map(str, (mode, labels, progress))), mode=mode, labels=labels, progress=progress)


def inputs(case):
    changed = 'ID,Value\nA01,11.25\nB02,13.75\n'
    mode = case['mode']
    if mode == 'replace': return {'Data.csv': changed, 'Removed.csv': INITIAL['Removed.csv']}
    if mode == 'add': return {**INITIAL, 'Other.csv': changed}
    if mode == 'remove': return {'Data.csv': changed}
    if mode == 'rename': return {'Renamed.csv': changed}
    if mode == 'empty': return {}
    if mode == 'header-only': return {'Empty.csv': 'ID,Value\n'}
    return {'Data.csv': changed, ('ZInvalid.csv' if mode == 'invalid-last' else 'AInvalid.csv'): 'NoSubject,Value\nx,19.25\n'}


def query(case):
    files = INITIAL if case['mode'].startswith('invalid') else inputs(case)
    parts = []
    for text in files.values():
        mapped_label = ('Original' if case['mode'].startswith('invalid') else
                        'Updated' if case['labels'] else None)
        mapping = '' if mapped_label is None else ('d[[1]]<-ifelse(d[[1]]=="A01",' + json.dumps(mapped_label) + ',d[[1]]); ')
        parts.append('local({d<-read.csv(text=' + json.dumps(text) +
            ',colClasses=c("character","numeric"),check.names=FALSE); ' + mapping +
            'c(d[[1]],as.character(d[[2]]),gsub("[^[:alpha:]]","",d[[1]]))})')
    return {'key': case['key'], 'code': 'c(' + ','.join(parts) + ')' if parts else 'character(0)'}


def expected(case, answers):
    files = INITIAL if case['mode'].startswith('invalid') else inputs(case)
    offset, tables = 0, {}
    for filename, text in files.items():
        count = max(0, len(text.splitlines()) - 1)
        if count:
            tables[Path(filename).stem] = pd.DataFrame({'AnimalName': answers[offset:offset+count],
                'Value': [float(value) for value in answers[offset+count:offset+2*count]],
                'Condition': answers[offset+2*count:offset+3*count]})
        else:
            tables[Path(filename).stem] = pd.DataFrame({name: pd.Series(dtype=object)
                                                      for name in ('AnimalName', 'Value', 'Condition')})
        offset += 3 * count
    assert offset == len(answers)
    return tables


def production(case, answers, folder):
    from PyFLASH.experiment import MiniExperiment
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    source = folder / 'source'
    source.mkdir()
    retired = folder / 'original-inputs'
    retired.mkdir()
    for name, text in INITIAL.items():
        (source / name).write_text(text, encoding='utf-8', newline='')
    (source / 'Condition Labels.csv').write_text('ID,Group\nA01,Original\n', encoding='utf-8')
    metadata = folder / 'calibration.txt'
    metadata.write_text('unchanged calibration source\n')
    exp = MiniExperiment('Original CSV refresh', str(source))
    with contextlib.redirect_stdout(io.StringIO()):
        exp.importCSVs(progress=case['progress'])
        exp.createSummary(progress=case['progress'])
    exp._declare_provenance_source(metadata, 'calibration')
    mapping = exp.data
    carriers = dict(exp.data)
    original_tables = {name: table(carrier.df) for name, carrier in exp.data.items()}
    summary = exp.summary
    original_summary = table(summary)
    old_labels = exp.condition_labels
    label_table = table(old_labels)
    old_sources = [dict(entry) for entry in exp._provenance_sources]
    # Preserve every synthetic original file outside the active input folder.
    for original in list(source.glob('*.csv')):
        assert original.resolve().is_relative_to(source.resolve())
        original.replace(retired / original.name)
    for name, text in inputs(case).items():
        (source / name).write_text(text, encoding='utf-8', newline='')
    if case['labels']:
        (source / 'Condition Labels.csv').write_text('ID,Group\nA01,Updated\n', encoding='utf-8')
    originals = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in list(source.glob('*.csv')) + list(retired.glob('*.csv')) + [metadata]}
    observed_error = None
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            result = exp.importCSVs(progress=case['progress'])
    except Exception as error:
        observed_error = type(error).__name__ + ': ' + str(error)
    try:
        assert exp.data is mapping
        predictions = expected(case, answers)
        assert list(exp.data) == sorted(predictions), (list(exp.data), sorted(predictions))
        for name, frame in predictions.items():
            pd.testing.assert_frame_equal(exp.data[name].df, frame, check_exact=True)
            assert exp.data[name].experiment is exp
        if case['mode'].startswith('invalid'):
            assert observed_error and observed_error.startswith('ValueError:')
            assert all(exp.data[name] is carrier for name, carrier in carriers.items())
            assert {name: table(carrier.df) for name, carrier in exp.data.items()} == original_tables
            assert exp.condition_labels is old_labels and table(exp.condition_labels) == label_table
            assert exp._provenance_sources == old_sources
        else:
            assert observed_error is None, observed_error
            assert result is exp.data
            labels = getattr(exp, 'condition_labels', None)
            if case['labels']:
                pd.testing.assert_frame_equal(labels, pd.DataFrame({'ID': ['A01'], 'Group': ['Updated']}), check_exact=True)
            else:
                assert labels is None
            expected_paths = {str(path.resolve()) for path in source.glob('*.csv')} | {str(metadata.resolve())}
            assert {entry['path'] for entry in exp._provenance_sources} == expected_paths
            assert all(entry['project_root'] == str(source) for entry in exp._provenance_sources)
        assert exp.summary is summary and table(exp.summary) == original_summary
        assert all(hashlib.sha256(Path(path).read_bytes()).hexdigest() == sha for path, sha in originals.items())
        return {'passed': True, 'actual': {name: table(carrier.df) for name, carrier in exp.data.items()},
                'error_observed': observed_error, 'sources': exp._provenance_sources}
    except Exception as error:
        return {'passed': False, 'error': type(error).__name__ + ': ' + str(error),
                'error_observed': observed_error, 'actual': {name: table(carrier.df) for name, carrier in exp.data.items()},
                'sources': exp._provenance_sources}


def freeze():
    import PyFLASH.experiment as module
    source = Path(module.__file__)
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    before = digest(source)
    output = OWNER / 'csv-refresh-original-v2'
    output.mkdir(exist_ok=False)
    items = list(cases())
    native = execute_queries([query(case) for case in items], output / 'native', name='csv-refresh-fields')
    rows = []
    for index, (case, result) in enumerate(zip(items, native['rows'], strict=True)):
        answers = values(result)
        rows.append({'case': case, 'native': result, 'expected': {name: table(frame) for name, frame in expected(case, answers).items()},
                     **production(case, answers, output / 'cases' / str(index))})
    assert digest(source) == before
    record = {'actual_calls': len(rows), 'failed': sum(not row['passed'] for row in rows),
              'source_unchanged': True, 'source_sha256': before, 'rows': rows}
    (output / 'before.json').write_text(json.dumps(record, indent=2) + '\n')
    (output / 'original-experiment.py').write_bytes(source.read_bytes())
    (output / 'original-reference.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps({key: record[key] for key in ('actual_calls', 'failed', 'source_unchanged')}), flush=True)


if __name__ == '__main__':
    freeze()
