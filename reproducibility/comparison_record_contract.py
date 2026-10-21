"""Complete unaudited group-record schema and scientific direction reports."""
from pathlib import Path
import hashlib,json
from reproducibility.group_description_reference import same as equal
from reproducibility import comparison_record_reference as reference
from reproducibility.comparison_record_adapter import production
FIXTURE=Path(__file__).with_name('fixtures')/'comparison_record_reference.json'


def cases():return json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']


def check_identity():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'));root=Path(__file__).parent
    for path,expected in fixture['source_manifest'].items():
        if hashlib.sha256((root/path).read_bytes()).hexdigest()!=expected:raise ValueError('Original record evidence changed: '+path)
    original=json.loads((root/fixture['before_path']).read_text(encoding='utf-8'))['rows']
    if fixture['rows']!=original:raise ValueError('Record requests or answers differ from before-correction evidence')
    if fixture['scientific_parent_complete'] is not False:raise ValueError('Unaudited records cannot certify every public-builder option')
    return fixture


def validate(output):
    from reproducibility.normality_association_validation import comparison
    check_identity();rows=[];paired=[]
    for case in cases():
        actual=production(case);answer=reference.report(case);unchanged=equal(answer,case['expected'])
        rows.append(comparison(case['key'],'independent-exact-group-moments/literal-report-schema-and-ordering',
            'complete-unaudited-record/all-fields-and-headline',actual,answer,unchanged and equal(actual,answer),unchanged,'all-fields/absolute-tolerance-zero',1e-9,0.))
        paired.append({'case':case,'production':actual,'reference':answer,'frozen_reference':case['expected']})
    (output/'comparison-records-paired.json').write_text(json.dumps({'rows':paired},indent=2,allow_nan=False),encoding='utf-8')
    return rows
