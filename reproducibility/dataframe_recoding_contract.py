"""Frozen single-step input recoding; broader constructor options remain open."""
from pathlib import Path
import hashlib
import json

ARCHIVE = Path(__file__).with_name('reference-sources') / 'dataframe-condition-recoding' / 'v1'
MANIFEST_SHA256 = '8ef45b12ff3bebf9ad1d05238db931c5b30196f242f3d769abae5280f69ea507'
CAPABILITY_PREFIXES = {'PyFLASH.dataframe.' + api: ('dataframe-recoding.' + api + '.',)
                       for api in ('from_dataframe', 'coerce_dataframe_input')}
COMPLETE_CAPABILITIES = frozenset()


def check_identity():
    manifest_path = ARCHIVE / 'source-manifest.json'
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != MANIFEST_SHA256:
        raise ValueError('Original condition recoding manifest changed')
    for name, digest in json.loads(manifest_path.read_text(encoding='utf-8')).items():
        if hashlib.sha256((ARCHIVE / name).read_bytes()).hexdigest() != digest:
            raise ValueError('Original condition recoding evidence changed: ' + name)
    fixture = json.loads((ARCHIVE / 'run.json').read_text(encoding='utf-8'))
    if fixture['comparisons'] != 18 or fixture['disagreements'] != 14 or fixture['source_changes']:
        raise ValueError('Original condition recoding probe scope changed')
    return fixture


def cases():
    return check_identity()['rows']


def production(row, output):
    import pandas as pd
    from PyFLASH import dataframe
    frame = pd.DataFrame(**row['input'])
    frame.index.name = 'original'
    frame.attrs = row['input_attrs'].copy()
    original = frame.copy(deep=True)
    parameters = dict(subject_col='Subject', factor_mappings={'Condition':row['mapping']},
                      file_path=str(Path(output) / row['key']))
    marker = None
    if row['marker_input'] is not None:
        marker = pd.DataFrame(**row['marker_input'])
        marker.attrs = {'client_marker':'literal-marker-recoding'}
        marker_original = marker.copy(deep=True)
        parameters['data'] = {'Cells':marker}
    if row['api'] == 'coerce_dataframe_input':
        parameters = dict(subject_col=parameters['subject_col'], factor_mappings=parameters['factor_mappings'],
            dataframe_kwargs={key:value for key,value in parameters.items() if key not in ('subject_col','factor_mappings')})
    result = getattr(dataframe, row['api'])(frame, **parameters)
    pd.testing.assert_frame_equal(frame, original, check_exact=True)
    assert frame.attrs == original.attrs
    if marker is not None:
        pd.testing.assert_frame_equal(marker, marker_original, check_exact=True)
        assert marker.attrs == marker_original.attrs
    return dict(summary=result.summary.to_dict(orient='split'),
        condition_names=[group.name for group in result.condition_list],
        marker=result.data['Cells'].df.to_dict(orient='split') if marker is not None else None,
        summary_index_name=result.summary.index.name, inputs_unchanged=True)


def expected(row):
    return dict(summary=row['expected'], condition_names=row['expected_condition_names'],
                marker=row['expected_marker'], summary_index_name='original', inputs_unchanged=True)


def validate(output):
    from PyFLASH._persistence import write_json
    from reproducibility.normality_association_validation import comparison
    check_identity()
    output = Path(output)
    rows, paired = [], []
    for case in cases():
        actual, error = None, None
        answer = expected(case)
        try:
            actual = production(case, output)
        except Exception as exc:
            error = type(exc).__name__ + ': ' + str(exc)
        agrees = error is None and actual == answer
        rows.append(comparison(case['key'], 'literal-single-step/native-pandas-map-and-metadata-join',
            'functional-condition-recoding/shared-pandas-integration/no-extra-estimator-vote',
            actual, answer, agrees, True, 'all-supplied-summary-and-marker-cells/condition-order/index/ownership', 0., 0.))
        paired.append(dict(case=case, actual=actual, expected=answer, error=error, agrees=agrees))
    write_json(output / 'dataframe-condition-recoding-paired.json', dict(rows=paired,
        complete_contract=False, independent_estimator_votes=0, scope=__doc__))
    return rows
