"""Complete emitted model reports preserve the source observations they describe."""
from pathlib import Path
import hashlib,json
from reproducibility.one_way_contract import equal
from reproducibility import comparison_parent_record_reference as reference
from reproducibility.comparison_parent_record_adapter import production
FIXTURE=Path(__file__).with_name('fixtures')/'comparison_parent_record_reference.json'


def cases():return json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']


def check_identity():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'));root=Path(__file__).parent
    original=json.loads((root/fixture['before_path']).read_text(encoding='utf-8'))['rows']
    if fixture['rows']!=original:raise ValueError('Emitted model requests or answers differ from before-correction evidence')
    from reproducibility.evidence_identity import verify_sources
    verify_sources(root, fixture)
    if fixture['scientific_parent_complete'] is not False:raise ValueError('Model record emission cannot certify every combined-parent option')
    return fixture


def validate(output):
    from reproducibility.normality_association_validation import comparison
    check_identity();rows=[];paired=[]
    for case in cases():
        actual=production(case);answer=reference.report(case);unchanged=equal(answer,case['expected'])
        rows.append(comparison(case['key'],'independent-complete-model-reports/exact-descriptions/literal-original-row-identities',
            'all-returned-fields/emitted-records/plotted-source-rows',actual,answer,unchanged and equal(actual,answer),unchanged,'all-fields/positive-probability-atol-zero',1e-9,0.))
        paired.append({'case':case,'production':actual,'reference':answer,'frozen_reference':case['expected']})
    (output/'comparison-parent-records-paired.json').write_text(json.dumps({'rows':paired},indent=2,allow_nan=False),encoding='utf-8')
    return rows
