"""Complete returned model reports use one retained-observation scope."""
from pathlib import Path
import hashlib,json
from reproducibility.one_way_contract import clean,equal
from reproducibility import comparison_parent_model_scope_reference as reference
from reproducibility.comparison_parent_model_scope_adapter import production
FIXTURE=Path(__file__).with_name('fixtures')/'comparison_parent_model_scope_reference.json'


def cases():return json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']


def check_identity():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'));root=Path(__file__).parent
    for path,expected in fixture['source_manifest'].items():
        if hashlib.sha256((root/path).read_bytes()).hexdigest()!=expected:
            raise ValueError('Original model-scope parent evidence changed: '+path)
    original=json.loads((root/fixture['before_path']).read_text(encoding='utf-8'))['rows']
    if fixture['rows']!=original:
        raise ValueError('Model-scope requests or answers differ from before-correction evidence')
    if fixture['scientific_parent_complete'] is not False:
        raise ValueError('This model-scope round cannot certify every public-parent option')
    return fixture


def validate(output):
    from reproducibility.normality_association_validation import comparison
    check_identity();rows=[];paired=[]
    for case in cases():
        actual=production(case);answer=reference.report(case);unchanged=equal(answer,case['expected'])
        rows.append(comparison(case['key'],'independent-common-fitted-row-scope/accepted-complete-model-equations',
            'complete-returned-model-parent-report/remaining-parent-options-not-certified',actual,answer,
            unchanged and equal(actual,answer),unchanged,'all-returned-fields/positive-probability-atol-zero',1e-9,0.))
        paired.append({'case':case,'production':actual,'reference':answer,'frozen_reference':case['expected']})
    (output/'comparison-parent-model-scope-paired.json').write_text(json.dumps({'rows':paired},indent=2,allow_nan=False),encoding='utf-8')
    return rows
