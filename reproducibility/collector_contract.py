"""Complete functional lifecycle, figure forwarding and live call ownership."""
from pathlib import Path
import json,hashlib
from reproducibility import collector_reference as reference
from reproducibility.collector_adapter import production
FIXTURE=Path(__file__).with_name('fixtures')/'collector_reference.json'
LIFECYCLE=('start','count','records_since','is_active','emit','collect')
CAPABILITIES=tuple('PyFLASH.report.'+name for name in (*LIFECYCLE,'attach','attachment_for','live_frame_ids'))


def cases():return json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']


def owners(case):
    names={'lifecycle':LIFECYCLE,'frames':('live_frame_ids','records_since'),
        'attachment':('attach','attachment_for'),'emission-attachment':('emit','attach','attachment_for','collect')}[case['variant']]
    return tuple('PyFLASH.report.'+name for name in names)


def check_identity():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'));root=Path(__file__).parent
    for name,digest in fixture['source_manifest'].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:raise ValueError('Original collector evidence changed: '+name)
    before=json.loads((root/fixture['before_path']).read_text(encoding='utf-8'))['rows']
    if fixture['rows']!=before:raise ValueError('Collector requests or answers differ from original evidence')
    first=json.loads((root/'reference-sources/collector/before-v1/frozen-before.json').read_text(encoding='utf-8'))['rows']
    if before[:465]!=first:raise ValueError('First collector round changed')
    if fixture['contract_kind']!='functional-complete-collector-lifecycle':raise ValueError('Collector state is a functional contract')
    return fixture


def validate(output):
    from reproducibility.normality_association_validation import comparison
    check_identity();rows=[];paired=[]
    for case in cases():
        actual=production(case);answer=reference.report(case);unchanged=answer==case['expected']
        rows.append(comparison(case['key'],'independent-event-ledger/literal-attachment-fields/Python-active-stack',
            'functional-complete-collector-lifecycle',actual,answer,unchanged and actual==answer,unchanged,'exact-state-records-and-attachments',0.,0.))
        paired.append({'case':case,'production':actual,'reference':answer,'frozen_reference':case['expected']})
    (output/'collector-paired.json').write_text(json.dumps({'rows':paired},indent=2,allow_nan=False),encoding='utf-8')
    return rows
