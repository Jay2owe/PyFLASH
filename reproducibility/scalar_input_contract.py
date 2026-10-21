"""Literal one-dimensional public sample contracts, frozen before correction."""
import hashlib,json
from pathlib import Path
FIXTURE=Path(__file__).with_name('fixtures')/'scalar_shape_reference.json'

def cases():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']

def production(case):
    from PyFLASH import stats_extra
    try:return {'result':getattr(stats_extra,case['method'])(**case['parameters'])}
    except Exception as error:return {'error':type(error).__name__}

def check_identity():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'))
    for path,expected in fixture['source_manifest'].items():
        if hashlib.sha256((Path(__file__).parent/path).read_bytes()).hexdigest()!=expected:
            raise ValueError('Original public-shape evidence changed: '+path)
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest()!=fixture['adapter_sha256']:
        raise ValueError('Public-shape reference adapter changed')
    return fixture

def validate(output):
    from reproducibility.normality_association_validation import comparison
    fixture=check_identity();rows=[];paired=[]
    for case in fixture['rows']:
        actual=production(case);expected=case['expected'];agrees=actual==expected
        rows.append(comparison(case['key'],'literal-ordered-one-dimensional-independent-samples',
            'functional-invalid-shape-preflight/no-additional-numerical-vote',actual,expected,
            agrees,True,'typed-invalid-shape-error',0.,0.))
        paired.append({'case':case,'production':actual,'reference':expected})
    (output/'scalar-shape-paired-data.json').write_text(json.dumps({'rows':paired},indent=2),encoding='utf-8')
    return rows
