"""Declared dataframe grouping/comparison requests, not whole constructors.

Literal client pair declarations cover direct, single-factor and crossed-factor
grouping through both constructors and public aliases. Full supplied tables,
group names, factor levels and caller ownership accompany every pair/refusal.
There is no fitted estimator or additional independent statistical vote.
"""
from pathlib import Path
import hashlib
import json

CAPABILITY_PREFIXES = {'PyFLASH.dataframe.'+api: ('dataframe-comparisons.'+api+'.',)
                       for api in ('from_dataframe','coerce_dataframe_input')}
COMPLETE_CAPABILITIES = frozenset()


ARCHIVE = Path(__file__).with_name('reference-sources') / 'dataframe-comparison-requests' / 'v1'
MANIFEST_SHA256 = '4aed01f9a9574019c8a45d452f393768db65f289cd17091240320e644b8c2e7d'


def check_identity():
    path = ARCHIVE / 'source-manifest.json'
    if hashlib.sha256(path.read_bytes()).hexdigest() != MANIFEST_SHA256:
        raise ValueError('Original comparison request manifest changed')
    for name,digest in json.loads(path.read_text(encoding='utf-8')).items():
        if hashlib.sha256((ARCHIVE/name).read_bytes()).hexdigest() != digest:
            raise ValueError('Original comparison request evidence changed: ' + name)
    original=json.loads((ARCHIVE/'run.json').read_text(encoding='utf-8'))
    if original['comparisons'] != 360 or original['disagreements'] != 104 or original['source_changes']:
        raise ValueError('Original comparison request scope changed')
    paired=json.loads((ARCHIVE/'dataframe-comparison-requests-paired.json').read_text(encoding='utf-8'))
    if len(paired['rows']) != 360:
        raise ValueError('Original comparison request cases changed')
    return paired['rows']


def cases():
    return [dict(row['case'],frozen_expected=row['expected']) for row in check_identity()]


def expected(row):
    return row['frozen_expected']


def production(row,output):
    import pandas as pd
    from PyFLASH import dataframe
    frame=pd.DataFrame({'Subject':['one','two','three'],'Treatment':['A','B','C'],
                        'Measured':[1.25,9.5,17.75]},index=[11,2,17])
    if row['design']=='crossed':
        frame['Sex']=['X','Y','X']
    frame.attrs={'literal_client':'declared-comparisons-v1'}
    original=frame.copy(deep=True)
    parameters={'subject_col':'Subject','file_path':str(Path(output)/row['key'])}
    if row['design']=='direct':
        parameters['group_col' if row['aliases'] else 'condition_col']='Treatment'
    else:
        parameters['group_cols' if row['aliases'] else 'factor_cols']=['Treatment','Sex'] if row['design']=='crossed' else ['Treatment']
    if row['aliases']:
        parameters.update(group_comparisons=row['pairs'],group_comparison_mode=row['mode'],group_control=row['control'])
    elif row['api']=='coerce_dataframe_input':
        parameters.update(condition_comparisons=row['pairs'],condition_comparison_mode=row['mode'],condition_control=row['control'])
    else:
        parameters.update(comparisons=row['pairs'],comparison_mode=row['mode'],control=row['control'])
    if row['api']=='coerce_dataframe_input':
        parameters['dataframe_kwargs']={'file_path':parameters.pop('file_path')}
    try:
        experiment=getattr(dataframe,row['api'])(frame,**parameters)
        actual=dict(refused=False,inputs_unchanged=True,summary=experiment.summary.to_dict(orient='split'),
                    names=[c.name for c in experiment.condition_list],pairs=experiment.condition_list.comparisons,
                    factor_levels={key:[c.name for c in values] for key,values in experiment.factorDict.items()})
    except ValueError:
        actual=dict(refused=True,inputs_unchanged=True)
    pd.testing.assert_frame_equal(frame,original,check_exact=True)
    assert frame.attrs==original.attrs
    return actual


def validate(output):
    from PyFLASH._persistence import write_json
    from reproducibility.normality_association_validation import comparison
    check_identity()
    records,paired=[],[]
    for row in cases():
        actual,error=None,None
        answer=expected(row)
        try:
            actual=production(row,output)
        except Exception as exc:
            error=type(exc).__name__+': '+str(exc)
        agrees=error is None and actual==answer
        records.append(comparison(row['key'],'literal-client-declared-group-pairs/full-supplied-cells',
            'functional-comparison-request/no-extra-estimator-vote',actual,answer,agrees,True,
            'exact-pairs/group-order/factor-levels/full-table/typed-refusal/input-ownership',0.,0.))
        paired.append(dict(case=row,actual=actual,expected=answer,error=error,agrees=agrees))
    write_json(Path(output)/'dataframe-comparison-requests-paired.json',dict(rows=paired,complete_contract=False,
        independent_estimator_votes=0,scope=__doc__))
    return records
