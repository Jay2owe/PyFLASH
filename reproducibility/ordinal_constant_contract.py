"""Partial fit contract: finite identical training rows, positive L2 penalty."""
from pathlib import Path
import hashlib,json
from reproducibility import ordinal_constant_reference as reference
from reproducibility.ordinal_constant_adapter import production
from reproducibility.ordinal_response_adapter import equal
FIXTURE=Path(__file__).with_name('fixtures')/'ordinal_constant_reference.json'

def cases():return json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']

def check_identity():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'));root=Path(__file__).parent
    from reproducibility.evidence_identity import verify_sources
    before=json.loads((root/fixture['before_path']).read_text(encoding='utf-8'))
    if fixture['rows']!=before['rows']:
        raise ValueError('Constant-feature requests or answers differ from original evidence')
    verify_sources(root, fixture)
    return fixture

def validate(output):
    from reproducibility.normality_association_validation import comparison
    check_identity();rows=[];paired=[]
    for row in cases():
        actual=production(row['case']);answer=reference.report(row['case'])
        unchanged=equal(answer,row['expected'])
        rows.append(comparison(row['case']['key'],'independent-count-odds/positive-penalty-unique-optimum',
            'identical-training-rows/all-fit-and-held-out-fields',actual,answer,
            unchanged and equal(actual,answer),unchanged,'relative-tolerance/absolute-zero',1e-9,0.))
        paired.append({'case':row['case'],'production':actual,'reference':answer})
    (output/'ordinal-constant-paired.json').write_text(json.dumps({'rows':paired},indent=2,allow_nan=False),encoding='utf-8')
    return rows
