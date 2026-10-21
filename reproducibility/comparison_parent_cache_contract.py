"""Complete warm/cached parent reports follow changing two-factor design content."""
from pathlib import Path
import hashlib,json
from reproducibility.one_way_contract import equal
from reproducibility import comparison_parent_cache_reference as reference
from reproducibility.comparison_parent_cache_adapter import production
FIXTURE=Path(__file__).with_name('fixtures')/'comparison_parent_cache_reference.json'


def cases():return json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']


def check_identity():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'));root=Path(__file__).parent
    for path,expected in fixture['source_manifest'].items():
        if hashlib.sha256((root/path).read_bytes()).hexdigest()!=expected:
            raise ValueError('Original cached parent evidence changed: '+path)
    original=json.loads((root/fixture['before_path']).read_text(encoding='utf-8'))['rows']
    if fixture['rows']!=original:raise ValueError('Cached parent requests or answers differ from before-correction evidence')
    if fixture['scientific_parent_complete'] is not False:raise ValueError('This design-cache round cannot certify every public-parent option')
    return fixture


def validate(output):
    from reproducibility.normality_association_validation import comparison
    check_identity();rows=[];paired=[]
    for case in cases():
        actual=production(case);answer=reference.report(case);unchanged=equal(answer,case['expected'])
        rows.append(comparison(case['key'],'independent-complete-two-factor-report/literal-design-content-identity',
            'all-warm-and-cached-return-fields/design-content-round-only',actual,answer,
            unchanged and equal(actual,answer),unchanged,'all-returned-fields/positive-probability-atol-zero',1e-9,0.))
        paired.append({'case':case,'production':actual,'reference':answer,'frozen_reference':case['expected']})
    (output/'comparison-parent-cache-paired.json').write_text(json.dumps({'rows':paired},indent=2,allow_nan=False),encoding='utf-8')
    return rows
