"""Complete supplied-record Markdown rendering; no statistical engine vote."""
from pathlib import Path
import hashlib,json
from reproducibility import record_digest_reference as reference
from reproducibility.record_digest_adapter import production
FIXTURE=Path(__file__).with_name('fixtures')/'record_digest_reference.json'


def cases():return json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']


def check_identity():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'));root=Path(__file__).parent
    for name,digest in fixture['source_manifest'].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:raise ValueError('Original digest evidence changed: '+name)
    original=json.loads((root/fixture['before_path']).read_text(encoding='utf-8'))['rows']
    if fixture['rows']!=original:raise ValueError('Digest requests or answers differ from original evidence')
    if fixture['contract_kind']!='functional-complete-Markdown-digest':raise ValueError('Digest rendering is a functional contract')
    return fixture


def validate(output):
    from reproducibility.normality_association_validation import comparison
    check_identity();rows=[];paired=[]
    for case in cases():
        actual=production(case);answer=reference.report(case);unchanged=answer==case['expected']
        rows.append(comparison(case['key'],'literal-complete-Markdown-template/accepted-input-records',
            'functional-complete-Markdown-digest',actual,answer,unchanged and actual==answer,unchanged,'exact-complete-text',0.,0.))
        paired.append({'case':case,'production':actual,'reference':answer,'frozen_reference':case['expected']})
    (output/'record-digests-paired.json').write_text(json.dumps({'rows':paired},indent=2,allow_nan=False),encoding='utf-8')
    return rows
