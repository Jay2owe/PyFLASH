"""Fresh exact rank counting, Gaussian tails and unchanged native R tests."""
from pathlib import Path
import json,math
from reproducibility import mann_whitney_contract as contract
from reproducibility import mann_whitney_mathematical_reference as mathematics
from reproducibility.normality_association_validation import comparison
from reproducibility.reference_runtime import execute_queries,values
NATIVE=Path(__file__).with_name('fixtures')/'mann_whitney_native_reference.json'

def native_cases():return json.loads(NATIVE.read_text(encoding='utf-8'))['rows']

def native_equal(actual,expected):
    expected=[float(v) if isinstance(v,str) else v for v in expected]
    return len(actual)==len(expected) and all((math.isnan(a) and math.isnan(b)) or a==b
        or math.isclose(a,b,rel_tol=1e-9,abs_tol=0. if i==1 else 1e-12) for i,(a,b) in enumerate(zip(actual,expected)))

def validate(output):
    fixture=contract.check_identity();rows=[];paired=[]
    for case in fixture['rows']:
        actual=contract.production(case['parameters']);answer=mathematics.reference(case['parameters'])
        unchanged=contract.equal(answer,case['expected']);agrees=unchanged and contract.equal(actual,answer)
        rows.append(comparison(case['key'],'exact-rational-ranks/subset-counting/80-digit-Gaussian-tails',
            'complete-rank-sum-report',actual,answer,agrees,unchanged,'all-fields/probability-atol-zero',1e-9,1e-12))
        paired.append({'case':case,'production':actual,'reference':answer,'frozen_reference':case['expected']})
    native_fixture=json.loads(NATIVE.read_text(encoding='utf-8'))
    native=execute_queries([r['query'] for r in native_fixture['rows']],output/'native-r-mann-whitney',name='mann-whitney-complete',timeout=300)
    for key,expected in native_fixture['native_runtime'].items():
        if native[key]!=expected:raise ValueError('Native rank-sum runtime changed: '+key)
    observed={r['key']:r for r in native['rows']};diagnostics=[]
    for case in native_fixture['rows']:
        actual=values(observed[case['query']['key']]);answer=case['expected']
        if case['role']!='independent-native-corroboration':
            diagnostics.append({'case':case,'native':mathematics.clean(actual),'reason':case['role']});continue
        agrees=native_equal(actual,answer)
        rows.append(comparison(case['query']['key'],'unchanged-R-stats-wilcox.test',
            'native-rank-sum-corroboration/group-exchange-symmetry-no-extra-kernel-vote',mathematics.clean(actual),answer,
            agrees,True,'statistic-probability/probability-atol-zero',1e-9,1e-12))
    (output/'mann-whitney-paired-data.json').write_text(json.dumps({'rows':paired,'native_diagnostics':diagnostics,
        'probability_absolute_tolerance':0.},indent=2,allow_nan=False),encoding='utf-8')
    return rows
