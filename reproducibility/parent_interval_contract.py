"""Complete interval-enabled returned reports; other parent options remain open."""
from pathlib import Path
import hashlib,json
from reproducibility import parent_interval_reference as reference
from reproducibility.parent_interval_adapter import production
from reproducibility.one_way_contract import equal
FIXTURE=Path(__file__).with_name('fixtures')/'parent_interval_reference.json'
CAPABILITY='PyFLASH.stats.multipleComparisons'

def cases():return json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']

def check_identity():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'));root=Path(__file__).parent
    for name,digest in fixture['source_manifest'].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Original parent interval evidence changed: '+name)
    original=json.loads((root/fixture['before_path']).read_text(encoding='utf-8'))['rows']
    if fixture['rows']!=original:
        raise ValueError('Parent interval requests or answers differ from original evidence')
    if fixture['scientific_parent_complete'] is not False:
        raise ValueError('Enabled intervals alone cannot certify the complete parent')
    if len(original)!=4187 or sum(row['default_count'] for row in original)!=7:
        raise ValueError('Complete parent interval case set changed')
    return fixture

def validate(output):
    from reproducibility.normality_association_validation import comparison
    check_identity();rows=[];paired=[]
    for case in cases():
        actual=production(case);answer=reference.report(case)
        unchanged=equal(answer,case['expected'])
        rows.append(comparison(case['key'],'accepted-independent-point-reports/exact-float-effects/independent-BCa-equations',
            'all-returned-parent-fields-with-intervals-enabled',actual,answer,
            unchanged and equal(actual,answer),unchanged,'complete-fields/positive-probability-atol-zero',1e-9,0.))
        paired.append({'case':case,'production':actual,'reference':answer,'frozen_reference':case['expected']})
    (output/'parent-intervals-paired.json').write_text(json.dumps({'rows':paired},indent=2,allow_nan=False),encoding='utf-8')
    return rows
