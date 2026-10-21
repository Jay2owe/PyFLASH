"""Retain native zero-row shapes and actual empty parent calls before repair."""
from pathlib import Path
from itertools import product
import contextlib, io, json, hashlib
import pandas as pd
from reproducibility.reference_runtime import execute_queries, values
from reproducibility.scientific_utility_contract import table

OWNER = Path(__file__).with_name('empty-parent-independent-20261008-v1')


def cases():
    for kind, storage, indexed, rois, raw in product(('main', 'mini'),
            ('absent', 'object', 'float64', 'string'), (False, True), (1, 2), (0, 2)):
        yield dict(key='.'.join(map(str, (kind, storage, indexed, rois, raw))),
                   kind=kind, storage=storage, indexed=indexed, rois=rois, raw=raw)
    for factors, images, progress in product((False, True), (False, True), (False, True)):
        yield dict(key='.'.join(map(str, ('batch', factors, images, progress))),
                   kind='batch', factors=factors, images=images, progress=progress)


def frame(case):
    result = pd.DataFrame({'AnimalName': pd.Series(dtype=object),
                           'Measurement': pd.Series(dtype='float64')})
    if case['storage'] != 'absent':
        result['Condition'] = pd.Series(dtype=case['storage'])
    if case['indexed']:
        result = result.set_index('AnimalName')
    return result


def query(case):
    if case['kind'] == 'batch':
        columns = ['AnimalName', 'Condition', 'Treatment'] + (['Sex'] if case['factors'] else [])
    else:
        columns = list(frame(case).columns)
        if 'Condition' not in columns:
            columns.append('Condition')
        columns.append('Treatment')
    return dict(key=case['key'], code='local({d<-setNames(rep(list(character(0)),' +
        str(len(columns)) + '),c(' + ','.join(map(json.dumps, columns)) +
        ')); c(as.character(nrow(as.data.frame(d))), names(d), '
        'as.character(length(regmatches(character(0),regexpr("WT|KO",character(0))))))})')


def expected(case, answers):
    assert answers[0] == '0' and answers[-1] == '0'
    columns = answers[1:-1]
    if case['kind'] == 'batch':
        return pd.DataFrame({name: pd.Series(dtype=object) for name in columns})
    result = frame(case)
    if 'Condition' not in result:
        result['Condition'] = pd.Series(index=result.index, dtype=object)
    result['Treatment'] = pd.Series(index=result.index,
        dtype='string' if case['storage'] == 'string' else object)
    assert list(result.columns) == columns
    return result


def production(case, answers, folder):
    from PyFLASH.experiment import Experiment, MiniExperiment
    from PyFLASH.batch import Batch
    from PyFLASH.conditions import condition, conditionList, zipConditionLists
    from PyFLASH.markers import Attribute
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    conditions = conditionList([condition(label, label, None, 'Treatment')
        for label in ('WT', 'KO')])
    if case['kind'] == 'batch' and case['factors']:
        sex = conditionList([condition(label, label, None, 'Sex') for label in ('F', 'M')])
        conditions = conditionList(zipConditionLists(conditions, sex))
    target = expected(case, answers)
    if case['kind'] == 'batch':
        experiment = Batch('Original empty batch', [], conditions, str(folder))
        originals, raw_originals = {}, {}
    else:
        cls = Experiment if case['kind'] == 'main' else MiniExperiment
        experiment = cls('Original empty condition tables', str(folder))
        experiment.summaries = {name: frame(case) for name in ('SCN', 'OC')[:case['rois']]}
        experiment.data = {}
        for index in range(case['raw']):
            rawcase = dict(case, indexed=False)
            carrier = Attribute(str(index), frame(rawcase), experiment)
            carrier.df = frame(rawcase)
            experiment.data[str(index)] = carrier
        originals = dict(experiment.summaries)
        raw_originals = {name: carrier.df for name, carrier in experiment.data.items()}
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            returned = (experiment.processData(import_images=case['images'], progress=case['progress'])
                if case['kind'] == 'batch' else experiment.set_condition_list(conditions))
        for name, actual in experiment.summaries.items():
            pd.testing.assert_frame_equal(actual, target, check_exact=True)
            if originals:
                assert actual is originals[name]
        if case['kind'] == 'batch':
            assert returned is None and experiment.data == {} and experiment.markers == set()
            assert experiment.experiment_list == [] and experiment.imagesDict == {}
            assert experiment.summary is experiment.summaries['SCN']
            assert experiment.master_region.empty
            assert list(experiment.master_region) == ['AnimalName', 'Region', 'ImageROI']
            if case['images']:
                images = pd.DataFrame(columns=['AnimalName', 'Marker', 'ROI', 'ImageName', 'ImagePath', 'Extension'])
                pd.testing.assert_frame_equal(experiment.images, images, check_exact=True)
            else:
                assert experiment.images is None
        else:
            assert returned is conditions
            for name, carrier in experiment.data.items():
                rawcase = dict(case, indexed=False)
                raw_target = frame(rawcase)
                if 'Condition' in raw_target:
                    raw_target['Treatment'] = pd.Series(dtype='string' if case['storage'] == 'string' else object)
                pd.testing.assert_frame_equal(carrier.df, raw_target, check_exact=True)
                assert carrier.df is raw_originals[name] and carrier.experiment is experiment
        assert experiment.condition_list is conditions
        return dict(passed=True, actual={name: table(value) for name, value in experiment.summaries.items()},
                    raw_actual={name: table(carrier.df) for name, carrier in experiment.data.items()})
    except Exception as error:
        return dict(passed=False, error=type(error).__name__ + ': ' + str(error),
                    actual={name: table(value) for name, value in getattr(experiment, 'summaries', {}).items()},
                    raw_actual={name: table(carrier.df) for name, carrier in getattr(experiment, 'data', {}).items()})


def freeze():
    import PyFLASH.experiment as experiment, PyFLASH.batch as batch
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    sources = [Path(experiment.__file__), Path(batch.__file__)]
    before = {path.name: digest(path) for path in sources}
    output = OWNER / 'original-v2'
    output.mkdir(parents=True, exist_ok=False)
    items = list(cases())
    native = execute_queries([query(case) for case in items], output / 'native', name='empty-parent-tables')
    rows = []
    for case, result in zip(items, native['rows'], strict=True):
        answers = values(result)
        rows.append(dict(case=case, native=result, expected=table(expected(case, answers)),
                         **production(case, answers, output / 'calls' / case['key'])))
        (output / 'progress.json').write_text(json.dumps(rows, indent=2))
    assert before == {path.name: digest(path) for path in sources}
    record = dict(actual_calls=len(rows), failed=sum(not row['passed'] for row in rows),
                  sources=before, source_unchanged=True, rows=rows,
                  scope='Functional zero-observation schema and ownership controls; native R empty matching and table shapes. No nonempty scientific vote or whole-parent completion.')
    (output / 'before.json').write_text(json.dumps(record, indent=2) + '\n')
    for path in sources:
        (output / ('original-' + path.name)).write_bytes(path.read_bytes())
    (output / 'original-reference.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps({key: record[key] for key in ('actual_calls', 'failed', 'source_unchanged')}), flush=True)


if __name__ == '__main__':
    freeze()
