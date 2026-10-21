"""Partial full-estimator native controls; broader scientific coverage stays open.

Expected complete arrays are unchanged original native fitter outputs. The
32 exact-zero cases have one exact native fitter plus separate optimality
proofs; the32 nonzero cases have two independent native fitting agreements.
Neither mathematical libraries nor a product-side solver add fitting votes.
"""
from pathlib import Path
import json

from reproducibility.evidence_identity import verify_sources
from reproducibility.ordinal_response_adapter import equal

FIXTURE=Path(__file__).with_name('fixtures')/'ordinal_fitting_reference.json'
CAPABILITIES=tuple('PyFLASH.modelling._PyFLASHOrdinalLogistic.'+name
                   for name in ('fit','predict','predict_proba'))


def check_identity():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'))
    if fixture.get('schema_version')!=1 or fixture.get('contract_kind')!='partial-whole-estimator-native-precision':
        raise ValueError('Unsupported ordinal fitting evidence schema')
    root=Path(__file__).parent
    verify_sources(root,fixture)
    original=json.loads((root/fixture['original_48_path']).read_text(encoding='utf-8'))
    retained=json.loads((root/fixture['retained_12_path']).read_text(encoding='utf-8'))
    additional=[]
    for name in fixture.get('additional_native_paths',[]):
        additional.extend(json.loads((root/name).read_text(encoding='utf-8')))
    if fixture['rows']!=original+retained+additional:
        raise ValueError('Ordinal fitting answers differ from unchanged native evidence')
    aliases=json.loads((root/fixture['historical_aliases_path']).read_text(encoding='utf-8'))
    historical=json.loads((root/fixture['historical_answers_path']).read_text(encoding='utf-8'))['rows']
    if len(aliases)!=len(historical) or any(alias['full_request']!=old['request'] or alias['original_answer']!=old['original']
                                           for alias,old in zip(aliases,historical,strict=True)):
        raise ValueError('Original ordinal fitting requests or answers changed')
    if fixture['rtol']!=1e-9 or fixture['atol']!=0:
        raise ValueError('Ordinal fitting comparison allowance changed')
    return fixture


def cases():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']


def historical_cases():
    fixture=check_identity()
    return json.loads((Path(__file__).parent/fixture['historical_aliases_path']).read_text(encoding='utf-8'))


def observe(case,*,container='array',dtype='float64',first_label=0,max_iter=10000,cls=None):
    """Call actual fitting and both responses over training and held-out rows."""
    import numpy as np
    import pandas as pd
    from scipy import sparse
    if cls is None:
        from PyFLASH.modelling import _PyFLASHOrdinalLogistic as cls
    x=np.asarray(case['x'],dtype=dtype)
    labels=np.asarray(case['y'],dtype=int)+first_label
    response=np.vstack((x,np.asarray(case['heldout'],dtype=dtype)))
    if container=='dataframe':
        x,response=pd.DataFrame(x),pd.DataFrame(response)
    elif container in ('csr','csc'):
        make=sparse.csr_matrix if container=='csr' else sparse.csc_matrix
        x,response=make(x),make(response)
    elif container!='array':
        raise ValueError('Unknown ordinal fitting test container')
    before=x.toarray().copy() if sparse.issparse(x) else np.asarray(x).copy()
    labels_before=labels.copy()
    model=cls(alpha=case['alpha'],max_iter=max_iter)
    returned=model.fit(x,labels)
    actual=dict(coefficients=model.model_.coef_.tolist(),thresholds=model.model_.theta_.tolist(),
                probabilities=model.predict_proba(response).tolist(),predictions=model.predict(response).tolist())
    if returned is not model or model.get_params()!=dict(alpha=case['alpha'],max_iter=max_iter):
        raise AssertionError('Ordinal fitting changed estimator/parameter ownership')
    if model.classes_.tolist()!=list(range(first_label,first_label+case['classes'])):
        raise AssertionError('Ordinal fitting changed class labels')
    if not np.array_equal(before,x.toarray() if sparse.issparse(x) else np.asarray(x)) or not np.array_equal(labels,labels_before):
        raise AssertionError('Ordinal fitting changed supplied inputs')
    diagnostics=getattr(model,'_ordinal_fit_diagnostics',None)
    if diagnostics is not None and diagnostics['initial_iterations']+diagnostics['refinement_iterations']>max_iter:
        raise AssertionError('Ordinal fitting exceeded the user optimization iteration limit')
    return actual


def expected_for_label(row,first_label):
    expected=dict(row['expected'])
    expected['predictions']=[value+first_label for value in expected['predictions']]
    return expected


def validate(output):
    """Score authenticated unchanged native arrays without manufacturing a vote."""
    import traceback
    from reproducibility.normality_association_validation import comparison
    fixture=check_identity();rows=[];paired=[]

    def score(key,reference,family,expected,request,**options):
        record=dict(request,unchanged_native=expected,error=None)
        try:
            actual=observe(request['case'],**options)
            agrees=equal(actual,expected)
        except Exception as error:
            actual={'error':type(error).__name__+': '+str(error)}
            agrees=False
            record['error']=traceback.format_exc()
        record['production']=actual
        paired.append(record)
        rows.append(comparison(key,reference,family,actual,expected,agrees,True,
                               'relative-tolerance/absolute-zero',1e-9,0))

    for row in fixture['rows']:
        case=row['case'];expected=row['expected']
        exact_zero=all(value==0 for field in ('coefficients','thresholds') for value in expected[field])
        reference='original-native-H2O/exact-optimality-support' if exact_zero else 'original-independent-native-H2O/glmnet'
        score('ordinal-native-fit.'+case['key'],reference,
            'partial-full-estimator/all-coefficients-thresholds-training-heldout-probabilities-predictions',
            expected,dict(case=case,qualification=row['qualification']))
    native={row['case']['key']:row for row in fixture['rows']}
    for alias in historical_cases():
        row=native[alias['numeric_case_key']]
        expected=expected_for_label(row,alias['first_label'])
        score('ordinal-native-fit.'+alias['request_key'],'original-independent-native-H2O/glmnet',
            'partial-full-estimator/original-container-iteration-limit-and-complete-output',expected,
            dict(case=row['case'],alias=alias),container=alias['container'],
            first_label=alias['first_label'],max_iter=alias['max_iter'])
    (output/'ordinal-native-fit-paired.json').write_text(json.dumps(dict(rows=paired),indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return rows
