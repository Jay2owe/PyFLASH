"""Complete bar/point/SEM artists for supplied requests; other options open."""
from pathlib import Path
import hashlib,json
from reproducibility import mean_bars_reference as reference
from reproducibility.mean_bars_adapter import production,differences
FIXTURE=Path(__file__).with_name('fixtures')/'mean_bars_reference.json'
CAPABILITY='mean_bars'

def cases():return json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']

def check_identity():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'));root=Path(__file__).parent
    for name,digest in fixture['source_manifest'].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:raise ValueError('Mean-bar evidence changed: '+name)
    before=json.loads((root/fixture['before_path']).read_text(encoding='utf-8'))
    if fixture['rows']!=before['rows']:raise ValueError('Mean-bar requests or answers differ from original evidence')
    return fixture

def validate(output):
    from reproducibility.normality_association_validation import comparison
    check_identity();rows=[];paired=[]
    for case in cases():
        answer=reference.report(case);actual=production(case);unchanged=answer==case['expected']
        delta=differences(answer,actual,case['request']['points'])
        rows.append(comparison(case['key'],'exact-rational-moments/high-precision-sqrt',
            'public-bars/subject-points/outward-SEM/category-positions-and-labels',actual,answer,
            unchanged and not delta,unchanged,'relative-tolerance/no-absolute-zero-floor',1e-12,0.))
        paired.append({'case':case,'production':actual,'reference':answer,'differences':delta})
    (output/'mean-bars-paired.json').write_text(json.dumps({'rows':paired},indent=2,allow_nan=False),encoding='utf-8')
    return rows
