"""Fresh unchanged-R and independent 80-digit complete variance/t reports."""
from pathlib import Path
import json,math
from reproducibility import variance_student_contract as contract
from reproducibility import variance_student_mathematical_reference as mathematics
from reproducibility.normality_association_validation import comparison
from reproducibility.reference_runtime import execute_queries,values

NATIVE=Path(__file__).with_name('fixtures')/'variance_student_native_reference.json'

def native_cases():return json.loads(NATIVE.read_text(encoding='utf-8'))['rows']

def native_equal(actual,expected):
    expected=[float(v) if isinstance(v,str) else v for v in expected]
    return len(actual)==len(expected) and all((math.isnan(a) and math.isnan(b)) or a==b
        or math.isclose(a,b,rel_tol=1e-9,abs_tol=0. if i==1 else 1e-12) for i,(a,b) in enumerate(zip(actual,expected)))

def validate(output):
    fixture=contract.check_identity();rows=[];paired=[]
    for case in fixture['rows']:
        actual=contract.production(case['kind'],case['parameters'])
        answer=(mathematics.variance_report if case['kind']=='variance' else mathematics.student_report)(case['parameters'])
        unchanged=contract.equal(answer,case['expected']);agrees=unchanged and contract.equal(actual,answer)
        rows.append(comparison(case['key'],'exact-rational-geometry/80-digit-beta-gamma-normal-score-inference',
            'complete-variance-and-student-report',actual,answer,agrees,unchanged,'all-fields/probability-atol-zero',1e-9,1e-12))
        paired.append({'case':case,'production':actual,'reference':answer,'frozen_reference':case['expected']})
    native_fixture=json.loads(NATIVE.read_text(encoding='utf-8'))
    native=execute_queries([r['query'] for r in native_fixture['rows']],output/'native-r-variance-student',name='variance-student-complete',timeout=600)
    for key,expected in native_fixture['native_runtime'].items():
        if native[key]!=expected:raise ValueError('Native variance/t runtime changed: '+key)
    observed={r['key']:r for r in native['rows']};diagnostics=[]
    for case in native_fixture['rows']:
        actual=values(observed[case['query']['key']]);answer=case['expected']
        if case['role']!='independent-native-corroboration':
            diagnostics.append({'case':case,'native':mathematics.clean(actual),'reason':case['role']});continue
        agrees=native_equal(actual,answer)
        rows.append(comparison(case['query']['key'],'unchanged-car-3.1-3-or-R-stats',
            'native-variance-and-student-corroboration/common-exact-rank-inputs-no-extra-kernel-vote',mathematics.clean(actual),answer,
            agrees,True,'statistic-probability-df/probability-atol-zero',1e-9,1e-12))
    (output/'variance-student-paired-data.json').write_text(json.dumps({'rows':paired,'native_diagnostics':diagnostics,
        'probability_absolute_tolerance':0.},indent=2,allow_nan=False),encoding='utf-8')
    return rows
