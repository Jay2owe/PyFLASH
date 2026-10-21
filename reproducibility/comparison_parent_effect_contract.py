"""Whole parent reports include independently defined scale-stable point effects."""
from pathlib import Path
import hashlib,json
from reproducibility import comparison_parent_effect_reference as reference
from reproducibility.comparison_parent_effect_adapter import production
from reproducibility.comparison_parent_effect_comparison import equal
FIXTURE=Path(__file__).with_name('fixtures')/'comparison_parent_effect_reference.json'


def cases():return json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']


def check_identity():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'));root=Path(__file__).parent
    for path,expected in fixture['source_manifest'].items():
        if hashlib.sha256((root/path).read_bytes()).hexdigest()!=expected:
            raise ValueError('Original point-effect evidence changed: '+path)
    original=json.loads((root/fixture['before_path']).read_text(encoding='utf-8'))['rows']
    if fixture['rows']!=original:raise ValueError('Point-effect requests or answers differ from before-correction evidence')
    if fixture['scientific_parent_complete'] is not False:raise ValueError('Point effects cannot certify all parent options')
    if fixture['effect_absolute_tolerance']!=0.:raise ValueError('Positive point effects cannot be accepted as zero')
    return fixture


def validate(output):
    from reproducibility.normality_association_validation import comparison
    check_identity();rows=[];paired=[]
    for case in cases():
        actual=production(case);answer=reference.report(case);unchanged=equal(answer,case['expected'])
        rows.append(comparison(case['key'],'independent-exact-measurement-moments/ranks/accepted-parent-inference',
            'all-returned-inference-and-point-effect-fields/intervals-disabled',actual,answer,
            unchanged and equal(actual,answer),unchanged,'positive-probabilities-and-effects-atol-zero',1e-9,0.))
        paired.append({'case':case,'production':actual,'reference':answer,'frozen_reference':case['expected']})
    (output/'comparison-parent-effects-paired.json').write_text(json.dumps({'rows':paired},indent=2,allow_nan=False),encoding='utf-8')
    return rows
