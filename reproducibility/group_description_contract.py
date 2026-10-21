"""Every descriptive field agrees with exact moments and empirical quantiles."""
from pathlib import Path
import hashlib,json
from reproducibility import group_description_reference as reference
from reproducibility.group_description_adapter import production
equal=reference.same
FIXTURE=Path(__file__).with_name('fixtures')/'group_description_reference.json'


def cases():return json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']


def check_identity():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'));root=Path(__file__).parent
    for path,expected in fixture['source_manifest'].items():
        if hashlib.sha256((root/path).read_bytes()).hexdigest()!=expected:raise ValueError('Original description evidence changed: '+path)
    original=json.loads((root/fixture['before_path']).read_text(encoding='utf-8'))['rows']
    if fixture['rows']!=original:raise ValueError('Description requests or answers differ from before-correction evidence')
    return fixture


def validate(output):
    from reproducibility.normality_association_validation import comparison
    check_identity();rows=[];paired=[]
    for case in cases():
        actual=production(case);answer=reference.describe(case);unchanged=equal(answer,case['expected'])
        rows.append(comparison(case['key'],'independent-rational-moments/empirical-type-seven-quantiles',
            'complete-group-description/all-fields',actual,answer,unchanged and equal(actual,answer),unchanged,'all-fields/absolute-tolerance-zero',1e-9,0.))
        paired.append({'case':case,'production':actual,'reference':answer,'frozen_reference':case['expected']})
    (output/'group-descriptions-paired.json').write_text(json.dumps({'rows':paired},indent=2,allow_nan=False),encoding='utf-8')
    return rows
