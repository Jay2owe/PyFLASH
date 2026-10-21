"""Functional marker eligibility and API binding; no complete pipeline fit claim."""
from pathlib import Path
import json,hashlib
from reproducibility.group_normality_boundary_adapter import observe
FIXTURE=Path(__file__).with_name('fixtures')/'group_normality_boundary_reference.json'

def cases():return json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']

def check_identity():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'));root=Path(__file__).parent
    for path,expected in fixture['source_manifest'].items():
        if hashlib.sha256((root/path).read_bytes()).hexdigest()!=expected:raise ValueError('Original pipeline boundary evidence changed: '+path)
    original=json.loads((root/fixture['before_path']).read_text(encoding='utf-8'))['rows']
    if fixture['rows']!=original:raise ValueError('Pipeline boundary inputs or requirements differ from before-correction evidence')
    return fixture

def validate(output):
    from reproducibility.normality_association_validation import comparison
    check_identity();rows=[];paired=[]
    for case in cases():
        observed=observe(case,output/'pipeline-boundaries'/case['key']);actual=observed['functional_observation']
        rows.append(comparison(case['key'],'literal-constant-marker-policy/actual-public-plot-signature',
            'functional-boundary-only/no-scientific-inference-vote',actual,case['reference'],observed['agrees'],True,'marker-eligibility-and-public-call-binding',0.,0.))
        paired.append({'case':case,'observed':observed})
    (output/'group-normality-boundary-paired.json').write_text(json.dumps({'rows':paired},indent=2,allow_nan=False),encoding='utf-8')
    return rows
