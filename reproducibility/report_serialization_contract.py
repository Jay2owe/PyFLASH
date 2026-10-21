"""Complete declared JSON-value and bounded-table summaries with literal answers."""
from pathlib import Path
import hashlib,json
from reproducibility import report_serialization_reference as reference
from reproducibility.report_serialization_adapter import production,decode
FIXTURE=Path(__file__).with_name('fixtures')/'report_serialization_reference.json'


def cases():return json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']


def capability(case):return 'PyFLASH.report.'+('coerce' if case['operation']=='coerce' else 'summarize_return')


def check_identity():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'));root=Path(__file__).parent
    for path,expected in fixture['source_manifest'].items():
        if hashlib.sha256((root/path).read_bytes()).hexdigest()!=expected:raise ValueError('Original serialization evidence changed: '+path)
    original=json.loads((root/fixture['before_path']).read_text(encoding='utf-8'))['rows']
    if fixture['rows']!=original:raise ValueError('Serialization requests or answers differ from before-correction evidence')
    if fixture['contract_kind']!='functional-bounded-summary':raise ValueError('Bounded summaries are not lossless scientific-data export')
    return fixture


def validate(output):
    from reproducibility.normality_association_validation import comparison
    check_identity();rows=[];paired=[]
    for case in cases():
        actual=production(case);answer=reference.report({**case,'input':decode(case['input'])});unchanged=answer==case['expected']
        rows.append(comparison(case['key'],'literal-complete-JSON-values-and-declared-200-row-table-schema',
            'functional-complete-bounded-summary',actual,answer,unchanged and actual==answer,unchanged,'exact-fields-types-and-values',0.,0.))
        paired.append({'case':case,'production':actual,'reference':answer,'frozen_reference':case['expected']})
    (output/'report-serialization-paired.json').write_text(json.dumps({'rows':paired},indent=2,allow_nan=False),encoding='utf-8')
    return rows
