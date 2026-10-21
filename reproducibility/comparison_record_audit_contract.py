"""Every complete audit-bearing record retains all accepted correction coordinates."""
from pathlib import Path
import hashlib,json
from reproducibility.group_description_reference import same as equal
from reproducibility import comparison_record_audit_reference as reference
from reproducibility.comparison_record_audit_adapter import production
FIXTURE=Path(__file__).with_name('fixtures')/'comparison_record_audit_reference.json'


def cases():return json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']


def required_keys():
    from reproducibility.comparison_record_contract import cases as unaudited_cases
    return {r['key'] for r in cases()+unaudited_cases()}


def check_identity():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'));root=Path(__file__).parent
    for path,expected in fixture['source_manifest'].items():
        if hashlib.sha256((root/path).read_bytes()).hexdigest()!=expected:raise ValueError('Original audited record evidence changed: '+path)
    original=json.loads((root/fixture['before_path']).read_text(encoding='utf-8'))['rows']
    if fixture['rows']!=original:raise ValueError('Audited record requests or answers differ from before-correction evidence')
    original_corrections=json.loads((root/'reference-sources/comparison-record-audits/original-correction-report-fixture.json').read_text(encoding='utf-8'))['rows']
    lookup={r['key']:r['expected'] for r in original_corrections}
    for row in fixture['rows']:
        if row['parameters']['correction_audit']!=lookup[row['audit_reference_key']]:raise ValueError('Accepted correction coordinates changed in record input')
    return fixture


def validate(output):
    from reproducibility.normality_association_validation import comparison
    check_identity();rows=[];paired=[]
    for case in cases():
        actual=production(case);answer=reference.report(case);unchanged=equal(answer,case['expected'])
        rows.append(comparison(case['key'],'independently-frozen-complete-correction-reports/literal-record-schema',
            'complete-audit-bearing-record/all-fields/accepted-arrays-reused',actual,answer,unchanged and equal(actual,answer),unchanged,'all-fields/absolute-tolerance-zero',1e-9,0.))
        paired.append({'case':case,'production':actual,'reference':answer,'frozen_reference':case['expected']})
    (output/'comparison-record-audits-paired.json').write_text(json.dumps({'rows':paired},indent=2,allow_nan=False),encoding='utf-8')
    return rows
