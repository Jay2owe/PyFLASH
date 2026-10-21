"""Complete finite-data reports with exact geometry beyond intermediate float range."""
from pathlib import Path
import json,hashlib,math
from reproducibility import one_way_contract as ordinary
from reproducibility import welch_one_way_contract as welch
from reproducibility import variance_student_contract as student
FIXTURE=Path(__file__).with_name('fixtures')/'extreme_inference_reference.json'
ARCHIVE=Path(__file__).with_name('reference-sources')/'extreme-inference'

def cases():return json.loads(FIXTURE.read_text())['rows']

def check_identity():
    fixture=json.loads(FIXTURE.read_text());root=Path(__file__).parent
    for path,expected in fixture['source_manifest'].items():
        if hashlib.sha256((root/path).read_bytes()).hexdigest()!=expected:raise ValueError('Original finite-geometry evidence changed: '+path)
    original=json.loads((ARCHIVE/'anova-before/frozen-before.json').read_text())['rows']
    original += [{**r,'family':'student'} for r in json.loads((ARCHIVE/'student-before/frozen-before.json').read_text())['rows']]
    if fixture['rows']!=original:raise ValueError('Finite-geometry inputs or answers differ from frozen before-correction evidence')
    return fixture

def equal(actual,expected):
    if isinstance(expected,dict):return isinstance(actual,dict) and actual.keys()==expected.keys() and all(equal(actual[key],expected[key]) for key in expected)
    if isinstance(expected,list):return isinstance(actual,list) and len(actual)==len(expected) and all(equal(a,b) for a,b in zip(actual,expected))
    if isinstance(actual,(float,int)) and isinstance(expected,(float,int)):return math.isclose(actual,expected,rel_tol=1e-9,abs_tol=0.)
    return type(actual)==type(expected) and actual==expected

def production(case):
    return ordinary.production(case) if case['family']=='ordinary' else welch.production(case) if case['family']=='welch' else student.production('student',case['parameters'])

def required_keys(family):return {r['key'] for r in cases() if r['family']==family}

def validate(output):
    from reproducibility import extreme_inference_mathematical_reference as mathematics
    from reproducibility.reference_runtime import execute_queries,values
    from reproducibility.normality_association_validation import comparison
    check_identity();rows=[];paired=[]
    queries=json.loads((ARCHIVE/'anova-before/extreme-log-range-moments-queries.json').read_text())
    native=execute_queries(queries,output/'native-range-moments',name='extreme-log-range-moments',timeout=900)
    original_native=json.loads((ARCHIVE/'anova-before/extreme-log-range-moments-results.json').read_text())
    for key in ('R','webR','wasm_sha256'):
        if native[key]!=original_native[key]:raise ValueError('Native extreme-moment runtime changed: '+key)
    fresh={r['key']:values(r)[0] for r in native['rows']}
    for case in cases():
        actual=production(case);answer=mathematics.report(case,fresh)
        unchanged=equal(answer,case['expected']);agrees=unchanged and equal(actual,answer)
        rows.append(comparison(case['key'],'exact-binary-geometry/80-digit-beta-tails/independent-Gaussian-range-moments',
            'complete-finite-geometry-report/no-additional-published-engine-vote',actual,answer,agrees,unchanged,
            'all-fields/zero-absolute-tolerance',1e-9,0.))
        paired.append({'case':case,'production':actual,'reference':answer,'frozen_reference':case['expected']})
    (output/'finite-geometry-paired-data.json').write_text(json.dumps({'rows':paired,'relative_tolerance':1e-9,'absolute_tolerance':0.},indent=2,allow_nan=False),encoding='utf-8')
    return rows
