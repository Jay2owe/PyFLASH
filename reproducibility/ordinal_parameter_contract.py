"""Complete estimator-parameter protocol; fitted methods remain separate."""
from pathlib import Path
import hashlib,json
from reproducibility.ordinal_parameter_reference import Reference,observe
from reproducibility.ordinal_parameter_adapter import production
FIXTURE=Path(__file__).with_name('fixtures')/'ordinal_parameter_reference.json'
CAPABILITIES=tuple('PyFLASH.modelling._PyFLASHOrdinalLogistic.'+name for name in ('get_params','set_params'))

def cases():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']

def check_identity():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'));root=Path(__file__).parent
    for name,digest in fixture['source_manifest'].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Original parameter evidence changed: '+name)
    original=json.loads((root/fixture['before_path']).read_text(encoding='utf-8'))
    if fixture['rows']!=original['rows']:
        raise ValueError('Parameter requests or answers differ from original evidence')
    if fixture['contract_kind']!='functional-complete-parameter-protocol':
        raise ValueError('Parameter protocol is not a fitted scientific contract')
    return fixture

def validate(output):
    from reproducibility.normality_association_validation import comparison
    check_identity();rows=[];paired=[]
    for case in cases():
        expected=observe(Reference,case);actual=production(case)
        preserved=expected==case['expected']
        rows.append(comparison(case['key'],'sklearn.BaseEstimator/parameter-protocol',
            'functional-complete-parameter-protocol',actual,expected,preserved and actual==expected,
            preserved,'exact-events-parameters-errors-and-attributes',0.,0.))
        paired.append({'case':case,'production':actual,'reference':expected,'frozen_reference':case['expected']})
    (output/'ordinal-parameters-paired.json').write_text(json.dumps({'rows':paired},indent=2,allow_nan=False),encoding='utf-8')
    return rows
