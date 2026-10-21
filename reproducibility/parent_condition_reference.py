"""Freeze literal factor-label controls before changing the parent assignment."""
from pathlib import Path
from itertools import product
import contextlib, io, json, hashlib
import pandas as pd
import numpy as np
from reproducibility.reference_runtime import execute_queries, values
from reproducibility.scientific_utility_contract import table

OWNER = Path(__file__).resolve().parent
LABELS = ['WT', 'A+B', 'A(B)', 'A[B]', 'A|B', 'A.B', 'A*B', 'A?B',
          'A^B', 'A$B', 'A{2}', 'A\\B', '[', '(', '\\', 'A/B']


def cases():
    for label, kind, indexed, tables, regions in product(LABELS, ('main', 'mini'),
            (False, True), (1, 3), (1, 2)):
        yield dict(key='.'.join(map(str, (LABELS.index(label), kind, indexed, tables, regions))),
                   label=label, kind=kind, indexed=indexed, tables=tables, regions=regions)


def frame(case, summary=False):
    result = pd.DataFrame({'AnimalName': ['WT1', 'KO2', 'WT3', 'KO4', 'WT5', 'WT6', 'KO7'],
        'Measurement': [1., 2., 3., 4., 5., 6., 7.],
        'Condition': [case['label'], 'prefix-' + case['label'] + '-suffix', 'AB', 'Control', 'Unknown', None, '']})
    if summary:
        result.loc[5:, 'Condition'] = ['WT', 'KO']
        if case['indexed']:
            result = result.set_index('AnimalName')
    return result


def query(case):
    observations = frame(case, summary=True)['Condition'].tolist() + frame(case)['Condition'].tolist()
    observations = ['NA_character_' if value is None else json.dumps(value) for value in observations]
    labels = [case['label'], 'Control']
    return {'key': case['key'], 'code': 'local({labels<-c(' + ','.join(map(json.dumps, labels)) +
        '); observations<-c(' + ','.join(observations) + '); vapply(observations,function(text){'
        'if(is.na(text)) return(NA_character_); positions<-vapply(labels,function(label) '
        'as.integer(regexpr(label,text,fixed=TRUE)[1]),integer(1)); '
        'valid<-which(positions>0); if(!length(valid)) return(NA_character_); '
        'labels[valid[which.min(positions[valid])]]},character(1))})'}


def expected(case, answers):
    summary, raw = frame(case, True), frame(case)
    summary['Treatment'] = pd.Series([np.nan if value is None else value for value in answers[:7]],
                                    index=summary.index, dtype=object)
    raw['Treatment'] = pd.Series([np.nan if value is None else value for value in answers[7:]], dtype=object)
    return summary, raw


def production(case, answers):
    from PyFLASH.experiment import Experiment, MiniExperiment
    from PyFLASH.conditions import condition, conditionList
    from PyFLASH.markers import Attribute
    cls = Experiment if case['kind'] == 'main' else MiniExperiment
    experiment = cls('Original literal factor ownership', str(OWNER))
    # The native query supplies labels only; every other field is retained input.
    original_summary = frame(case)
    if case['indexed']:
        original_summary = original_summary.set_index('AnimalName')
    experiment.summaries = {name: original_summary.copy() for name in ('SCN', 'OC')[:case['regions']]}
    experiment.summary = experiment.summaries['SCN']
    experiment.data = {str(i): Attribute(str(i), frame(case), experiment) for i in range(case['tables'])}
    # Attribute creation derives its own default condition. These controls
    # explicitly supply the already-authored conditions to the target method.
    for carrier in experiment.data.values():
        carrier.df = frame(case)
    originals = {name: value for name, value in experiment.summaries.items()}
    raw_originals = {name: value.df for name, value in experiment.data.items()}
    conditions = conditionList([condition(label, label, None, 'Treatment') for label in (case['label'], 'Control')])
    expect, raw = expected(case, answers)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            returned = experiment.set_condition_list(conditions)
        for name, result in experiment.summaries.items():
            pd.testing.assert_frame_equal(result, expect, check_exact=True)
            assert result is originals[name]
        for name, carrier in experiment.data.items():
            pd.testing.assert_frame_equal(carrier.df, raw, check_exact=True)
            assert carrier.df is raw_originals[name] and carrier.experiment is experiment
        assert experiment.summary is experiment.summaries['SCN']
        assert returned is experiment.condition_list is conditions
        return {'passed': True, 'actual': {name: table(value) for name, value in experiment.summaries.items()},
                'raw_actual': {name: table(value.df) for name, value in experiment.data.items()}}
    except Exception as error:
        return {'passed': False, 'error': type(error).__name__ + ': ' + str(error),
                'actual': {name: table(value) for name, value in experiment.summaries.items()},
                'raw_actual': {name: table(value.df) for name, value in experiment.data.items()}}


def freeze():
    import PyFLASH.experiment as module
    source = Path(module.__file__)
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    before = digest(source)
    output = OWNER / 'parent-conditions-original-v2'
    output.mkdir(exist_ok=False)
    items = list(cases())
    native = execute_queries([query(case) for case in items], output / 'native', name='literal-factor-labels')
    rows = []
    for case, result in zip(items, native['rows'], strict=True):
        answers = values(result)
        expect, raw = expected(case, answers)
        rows.append({'case': case, 'native': result, 'expected': table(expect), 'raw_expected': table(raw),
                     **production(case, answers)})
    assert digest(source) == before
    record = {'actual_calls': len(rows), 'failed': sum(not row['passed'] for row in rows),
              'source_unchanged': True, 'source_sha256': before, 'rows': rows}
    (output / 'before.json').write_text(json.dumps(record, indent=2) + '\n')
    (output / 'original-experiment.py').write_bytes(source.read_bytes())
    (output / 'original-reference.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps({key: record[key] for key in ('actual_calls', 'failed', 'source_unchanged')}), flush=True)


if __name__ == '__main__':
    freeze()
