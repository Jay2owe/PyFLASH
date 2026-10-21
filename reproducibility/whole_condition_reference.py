"""Native categorical assignment for every declared parent branch before repair."""
from pathlib import Path
from itertools import product
from types import SimpleNamespace
import contextlib, io, json, hashlib, shutil, subprocess, sys
import numpy as np
import pandas as pd
from reproducibility.reference_runtime import execute_queries, values as native_values
from reproducibility.scientific_utility_contract import table as base_table

OWNER = Path(__file__).with_name('parent-condition-whole-independent-20261008-v2')


def values(row):
    # R NA_character_ is a missing label/row match, not a floating-point datum.
    return [None if pd.isna(value) else value for value in native_values(row)]


def table(frame):
    result = base_table(frame)
    result['rows'] = [['NaN' if value is pd.NA else value for value in row] for row in result['rows']]
    return result
LEVELS = {
    'ordinary': [('Treatment', ['WT', 'KO']), ('Sex', ['F', 'M']), ('Protocol', ['T', 'C'])],
    'literal': [('Treatment', ['A+B', 'A(B)']), ('Sex', ['[F]', 'M|M']), ('Protocol', ['T.C', 'C\\C'])],
    'overlap': [('Treatment', ['W', 'WT']), ('Sex', ['F', 'FT']), ('Protocol', ['T', 'TT'])],
    'unicode': [('Treatment', ['α', 'β']), ('Sex', ['F', 'M']), ('Protocol', ['T', 'C'])],
}


def cases():
    for style, factors, storage, indexed, images, raw, rois in product(LEVELS, (1, 2, 3),
            ('absent', 'object', 'string'), (False, True), ('absent', 'empty', 'stale'), (False, True), (1, 2)):
        yield dict(key='.'.join(map(str, (style, factors, storage, indexed, images, raw, rois))),
            style=style, factors=factors, storage=storage, indexed=indexed, images=images, raw=raw, rois=rois)


def labels(case):
    return LEVELS[case['style']][:case['factors']]


def subjects(case):
    levels = labels(case)
    first = ''.join(pair[0] for _, pair in levels)
    second = ''.join(pair[1] for _, pair in levels)
    return [first + '1', second + '2', first + '3', 'Unknown4', first + '1']


def frame(case, raw=False):
    ids = subjects(case)
    result = pd.DataFrame({'AnimalName': ids, 'Measurement': [1.25, 2.5, 3.75, 5., 6.25]})
    result.attrs['original'] = {'units': 'retained', 'replicates': [1, 2]}
    if case['storage'] != 'absent' or raw and case['raw']:
        first = ''.join(pair[0] for _, pair in labels(case))
        condition = [first, None, '  ', 'Unknown', 'prefix-' + first + '-suffix']
        dtype = 'string' if case['storage'] == 'string' else object
        result['Condition'] = pd.Series(condition, dtype=dtype)
    if raw and not case['raw']:
        result = result.drop(columns='Condition', errors='ignore')
    if case['indexed'] and not raw:
        result = result.set_index('AnimalName')
    return result


def conditions(case, raw=False):
    supplied = frame(case, raw)
    ids = subjects(case)
    text = supplied['Condition'].tolist() if 'Condition' in supplied else [None] * len(ids)
    if not raw:
        text = [''.join(filter(str.isalpha, animal)) if pd.isna(value) or not str(value).strip() else str(value)
                for animal, value in zip(ids, text)]
    return [None if pd.isna(value) else str(value) for value in text]


def query(case):
    def literal(value):
        return 'NA_character_' if value is None else json.dumps(value, ensure_ascii=False)
    supplied = frame(case)
    supplied_text = supplied['Condition'].tolist() if 'Condition' in supplied else [None] * 5
    supplied_text = [None if pd.isna(value) else str(value) for value in supplied_text]
    setup = ('local({animal<-c(' + ','.join(map(literal, subjects(case))) + '); text<-c(' +
        ','.join(map(literal, supplied_text)) + '); missing<-is.na(text)|trimws(text)==""; '
        'text[missing]<-gsub("[^[:alpha:]]","",animal[missing]); ')
    snippets = ['text']
    for raw in (False, True):
        if raw and not case['raw']:
            continue
        text = conditions(case, raw) if raw else None
        for factor, levels in labels(case):
            snippets.append('local({labels<-c(' + ','.join(map(literal, levels)) +
                '); observations<-' + ('c(' + ','.join(map(literal, text)) + ')' if raw else 'text') +
                '; vapply(observations,function(text){if(is.na(text)) return(NA_character_); '
                'positions<-vapply(labels,function(label) as.integer(regexpr(label,text,fixed=TRUE)[1]),integer(1)); '
                'valid<-which(positions>0); if(!length(valid)) return(NA_character_); '
                'labels[valid[which.min(positions[valid])]]},character(1))})')
    # Native first-match row ownership supplies image metadata, including an
    # indexed subject table. All numeric measurements remain authored inputs.
    image_ids = [subjects(case)[1], subjects(case)[0], 'Missing5', subjects(case)[0]]
    snippets.append('as.character(match(c(' + ','.join(map(literal, image_ids)) + '),c(' +
                    ','.join(map(literal, subjects(case))) + ')))')
    return dict(key=case['key'], code=setup + 'c(' + ','.join(snippets) + ')})')


def expected(case, answers):
    summary, raw = frame(case), frame(case, True)
    dtype = 'string' if case['storage'] == 'string' else object
    summary['Condition'] = pd.Series(answers[:5], index=summary.index, dtype=dtype)
    offset = 5
    for target in (summary, raw):
        if target is raw and not case['raw']:
            continue
        for factor, levels in labels(case):
            target[factor] = pd.Series([pd.NA if value is None and dtype == 'string' else
                np.nan if value is None else value for value in answers[offset:offset+5]],
                index=target.index, dtype=dtype)
            offset += 5
    assert len(answers) == offset + 4
    images = image_frame(case)
    if case['images'] == 'stale':
        for column in ['Condition'] + [factor for factor, levels in labels(case)]:
            if column in images:
                images = images.drop(columns=column)
            selected = [np.nan if value is None else summary.iloc[int(value)-1][column]
                        for value in answers[offset:]]
            # A pandas left join retains nullable text for nullable inputs.
            images[column] = pd.Series(selected, dtype=dtype)
    return summary, raw, images


def image_frame(case):
    if case['images'] == 'absent':
        return None
    ids = [subjects(case)[1], subjects(case)[0], 'Missing5', subjects(case)[0]]
    if case['images'] == 'empty':
        ids = []
    images = pd.DataFrame({'AnimalName': pd.Series(ids, dtype=object),
        'Marker': pd.Series(['M'] * len(ids), dtype=object),
        'ImagePath': pd.Series(['literal/' + str(i) + '.png' for i in range(len(ids))], dtype=object),
        'Condition': pd.Series(['stale'] * len(ids), dtype=object)})
    for factor, levels in labels(case):
        images[factor] = pd.Series(['stale'] * len(ids), dtype=object)
    return images


def production(case, answers):
    from PyFLASH.experiment import Experiment
    from PyFLASH.conditions import condition, conditionList, zipConditionLists
    experiment = object.__new__(Experiment)
    experiment.name = 'Original complete parent condition assignment'
    experiment.summaries = {roi: frame(case) for roi in ('SCN', 'OC')[:case['rois']]}
    experiment.data = {str(i): SimpleNamespace(df=frame(case, True), experiment=experiment) for i in range(3)}
    experiment.images = image_frame(case)
    experiment.imagesDict = {'original': {'paths': ['literal']}}
    experiment._condition_unrelated = object()
    state = dict(experiment.__dict__)
    original_summaries = dict(experiment.summaries)
    original_raw = {key: carrier.df for key, carrier in experiment.data.items()}
    original_images = None if experiment.images is None else experiment.images.copy(deep=True)
    groups = None
    for factor, levels in labels(case):
        level_list = conditionList([condition(label, label, None, factor) for label in levels])
        groups = level_list if groups is None else conditionList(zipConditionLists(groups, level_list))
    target, raw_target, image_target = expected(case, answers)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            result = experiment.set_condition_list(groups)
        assert result is experiment.condition_list is groups
        assert experiment.conditions is groups.conditions and experiment.factor is groups.factor
        assert experiment.factorDict is groups.factorDict
        for key, actual in experiment.summaries.items():
            pd.testing.assert_frame_equal(actual, target, check_exact=True)
            assert actual is original_summaries[key]
        for key, carrier in experiment.data.items():
            pd.testing.assert_frame_equal(carrier.df, raw_target, check_exact=True)
            assert carrier.df is original_raw[key] and carrier.experiment is experiment
        if image_target is None:
            assert experiment.images is None
        else:
            pd.testing.assert_frame_equal(experiment.images, image_target, check_exact=True)
            pd.testing.assert_frame_equal(state['images'], original_images, check_exact=True)
            assert experiment.images is state['images'] if case['images'] == 'empty' else experiment.images is not state['images']
        assert experiment.imagesDict is state['imagesDict']
        assert experiment._condition_unrelated is state['_condition_unrelated']
        return dict(passed=True, summaries={key: table(value) for key, value in experiment.summaries.items()},
            raw={key: table(carrier.df) for key, carrier in experiment.data.items()},
            images=None if experiment.images is None else table(experiment.images))
    except Exception as error:
        return dict(passed=False, error=type(error).__name__ + ': ' + str(error),
            summaries={key: table(value) for key, value in experiment.summaries.items()},
            raw={key: table(carrier.df) for key, carrier in experiment.data.items()},
            images=None if experiment.images is None else table(experiment.images))


def freeze():
    import PyFLASH.experiment as module
    source = Path(module.__file__)
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    before = digest(source)
    output = OWNER / 'original'
    assert shutil.disk_usage(OWNER.parent).free >= 200 * 1024**2
    output.mkdir(parents=True, exist_ok=False)
    (output / 'rows').mkdir()
    items = list(cases())
    (output / 'original-experiment.py').write_bytes(source.read_bytes())
    (output / 'original-reference.py').write_bytes(Path(__file__).read_bytes())
    (output / 'inputs.json').write_text(json.dumps(items, indent=2) + '\n')
    native = execute_queries([query(case) for case in items], output / 'native', name='whole-parent-factor-assignment')
    rows = []
    for case, result in zip(items, native['rows'], strict=True):
        answers = values(result)
        summary, raw, images = expected(case, answers)
        rows.append(dict(case=case, native=result, expected=table(summary), raw_expected=table(raw),
            images_expected=None if images is None else table(images), **production(case, answers)))
        (output / 'rows' / (case['key'] + '.json')).write_text(
            json.dumps(rows[-1], indent=2, allow_nan=False) + '\n')
    assert digest(source) == before
    record = dict(actual_calls=len(rows), failed=sum(not row['passed'] for row in rows),
        source_unchanged=True, source_sha256=before, rows=rows,
        python=sys.version, producer_sha256=digest(Path(__file__)),
        commit=subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip(),
        scope='Direct parent condition method: every factor, summary/raw/image field, dtype and alias on these declared branches. Native R literal matching and first-subject image ownership. No downstream scientific pipeline vote.')
    (output / 'before.json').write_text(json.dumps(record, indent=2, allow_nan=False) + '\n')
    (output / 'original-experiment.py').write_bytes(source.read_bytes())
    (output / 'original-reference.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps({key: record[key] for key in ('actual_calls', 'failed', 'source_unchanged')}), flush=True)


if __name__ == '__main__':
    freeze()
