"""Frozen requested metadata identity; broader constructor options remain open."""
from pathlib import Path
import hashlib
import json

ARCHIVE = Path(__file__).with_name('reference-sources') / 'dataframe-metadata-ownership' / 'v1'
MANIFEST_SHA256 = '36d50c1c7110bb1b669c90e92a011fd77702947d05b40b8518215031f4298aef'
CAPABILITY_PREFIXES = {'PyFLASH.dataframe.' + api: ('dataframe-metadata.' + api + '.',)
                       for api in ('from_dataframe','coerce_dataframe_input')}
COMPLETE_CAPABILITIES = frozenset()


def check_identity():
    path = ARCHIVE / 'source-manifest.json'
    if hashlib.sha256(path.read_bytes()).hexdigest() != MANIFEST_SHA256:
        raise ValueError('Original measurement metadata manifest changed')
    for name,digest in json.loads(path.read_text(encoding='utf-8')).items():
        if hashlib.sha256((ARCHIVE/name).read_bytes()).hexdigest() != digest:
            raise ValueError('Original measurement metadata evidence changed: ' + name)
    fixture = json.loads((ARCHIVE/'run.json').read_text(encoding='utf-8'))
    if fixture['comparisons'] != 16 or fixture['disagreements'] != 8 or fixture['source_changes']:
        raise ValueError('Original metadata probe scope changed')
    return fixture


def cases():
    return check_identity()['rows']


def unpack(value):
    if isinstance(value,dict):
        if value == {'nonfinite':'nan'}:
            return float('nan')
        return {key:unpack(item) for key,item in value.items()}
    if isinstance(value,list):
        return [unpack(item) for item in value]
    return value


def pack(value):
    import math
    if isinstance(value,float) and math.isnan(value):
        return {'nonfinite':'nan'}
    if isinstance(value,dict):
        return {key:pack(item) for key,item in value.items()}
    if isinstance(value,(list,tuple)):
        return [pack(item) for item in value]
    return value


def production(row,output):
    import pandas as pd
    from PyFLASH import dataframe
    summary = pd.DataFrame(**unpack(row['input']))
    summary.index.name = 'original'
    summary.attrs = row['input_attrs'].copy()
    marker = pd.DataFrame(**unpack(row['marker_input']))
    marker.attrs = row['marker_attrs'].copy()
    snapshots = [frame.copy(deep=True) for frame in (summary,marker)]
    parameters = dict(subject_col='Subject',group_col='Treatment',file_path=str(Path(output)/row['key']),data={'Cells':marker})
    if row['api'] == 'coerce_dataframe_input':
        parameters = dict(subject_col='Subject',group_col='Treatment',
            dataframe_kwargs={key:value for key,value in parameters.items() if key not in ('subject_col','group_col')})
    result, error = None,None
    try:
        result = getattr(dataframe,row['api'])(summary,**parameters)
    except ValueError as exc:
        error = str(exc)
    for frame,snapshot in zip((summary,marker),snapshots):
        pd.testing.assert_frame_equal(frame,snapshot,check_exact=True)
        assert frame.attrs == snapshot.attrs
    if error is not None:
        return dict(ambiguity_refused=error.startswith('Cannot infer measurement metadata uniquely'),
                    error=error,inputs_unchanged=True)
    return dict(summary=pack(result.summary.to_dict(orient='split')),
                marker=pack(result.data['Cells'].df.to_dict(orient='split')),inputs_unchanged=True)


def expected(row):
    if row['native_error'] is not None:
        return dict(ambiguity_refused=True,inputs_unchanged=True)
    return dict(summary=row['expected_summary'],marker=row['expected_marker'],inputs_unchanged=True)


def equal(actual,answer):
    import pandas as pd
    if answer.get('ambiguity_refused'):
        return actual.get('ambiguity_refused') is True and actual['inputs_unchanged']
    if actual.keys() != answer.keys() or not actual['inputs_unchanged']:
        return False
    # Preserve raw None/NaN operands in the paired evidence. Native pandas
    # equality compares their unchanged missing status, all finite cells,
    # column types/order and exact row indexes; this adds no numeric allowance.
    return all(pd.DataFrame(**unpack(actual[key])).equals(pd.DataFrame(**unpack(answer[key])))
               for key in ('summary','marker'))


def validate(output):
    from PyFLASH._persistence import write_json
    from reproducibility.normality_association_validation import comparison
    check_identity()
    rows,paired = [],[]
    for row in cases():
        actual,error = None,None
        answer = expected(row)
        try:
            actual = production(row,output)
            agrees = equal(actual,answer)
        except Exception as exc:
            error = type(exc).__name__ + ': ' + str(exc)
            agrees = False
        rows.append(comparison(row['key'],'original-native-pandas-requested-many-to-one-join',
            'functional-measurement-identity/shared-pandas-integration/no-extra-estimator-vote',
            actual,answer,agrees,True,'complete-requested-metadata-and-measurement-cells/typed-ambiguity-refusal',0.,0.))
        paired.append(dict(case=row,actual=actual,expected=answer,error=error,agrees=agrees))
    write_json(Path(output)/'dataframe-metadata-ownership-paired.json',dict(rows=paired,
        complete_contract=False,independent_estimator_votes=0,scope=__doc__,
        original_difference_scope='Six assignment/refusal/dropped-row failures and two factor-context index-only join-convention differences.'))
    return rows
