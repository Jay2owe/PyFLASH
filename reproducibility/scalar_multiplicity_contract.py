"""Full public scalar correction requests with immutable independent answers."""
from pathlib import Path
import json,hashlib
import numpy as np
from PyFLASH import stats
from reproducibility.one_way_contract import clean,equal
from reproducibility import scalar_multiplicity_reference as reference
FIXTURE=Path(__file__).with_name('fixtures')/'scalar_multiplicity_complete_reference.json'
def cases():return json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']
def check_identity():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'));root=Path(__file__).parent
    for path,expected in fixture['source_manifest'].items():
        if hashlib.sha256((root/path).read_bytes()).hexdigest()!=expected:raise ValueError('Original scalar correction evidence changed: '+path)
    original=[row for path in fixture['before_rounds'] for row in json.loads((root/path).read_text(encoding='utf-8'))['rows']]
    if fixture['rows']!=original:raise ValueError('Scalar correction requests or answers differ from frozen before-correction evidence')
    return fixture
def production(case):
    parameters=dict(case['parameters'])
    for key,form in (('p_value',case.get('probability_form')),('n_tests',case.get('count_form'))):
        if form:parameters[key]=np.asarray([parameters[key]] if form=='array1' else parameters[key])
    try:return clean(getattr(stats,case['method'])(**parameters))
    except Exception as error:return {'error':type(error).__name__}
def validate(output):
    from reproducibility.normality_association_validation import comparison
    check_identity();rows=[];paired=[]
    for case in cases():
        actual=production(case);answer=reference.mathematical(case);unchanged=equal(answer,case['expected'])
        rows.append(comparison(case['key'],'exact-binary-probability-product/80-digit-Sidak-tail/literal-request-domain',
            'whole-public-scalar-correction/no-extra-native-vote',actual,answer,unchanged and equal(actual,answer),unchanged,'probability-atol-zero',1e-9,0.))
        paired.append({'case':case,'production':actual,'reference':answer,'frozen_reference':case['expected']})
    (output/'scalar-multiplicity-paired-data.json').write_text(json.dumps({'rows':paired},indent=2,allow_nan=False),encoding='utf-8')
    return rows
