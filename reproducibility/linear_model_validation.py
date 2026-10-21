"""Fresh whole reports and five unchanged published R coefficient/covariance matrices."""
from pathlib import Path
import json
from reproducibility import linear_model_contract as contract,linear_model_mathematical_reference as reference
from reproducibility.reference_runtime import execute_queries,values
from reproducibility.normality_association_validation import comparison
ARCHIVE=Path(__file__).with_name('reference-sources')/'linear-model-reports'
def native_cases():return json.loads((ARCHIVE/'native/frozen-before.json').read_text())['rows']
def required_keys():return {r['key'] for r in contract.cases()+native_cases()}
def validate(output):
    contract.check_identity();rows=[];paired=[]
    for case in contract.cases():
        actual=contract.production(case);answer=reference.report(case);unchanged=contract.equal(answer,case['expected'])
        rows.append(comparison(case['key'],'exact-rational-OLS/sandwiches/constraint-rank/80-digit-tails',
            'complete-model-parent-report',actual,answer,unchanged and contract.equal(actual,answer),unchanged,'all-numeric-fields-atol-zero',1e-9,0.))
        paired.append({'case':case,'production':actual,'reference':answer,'frozen_reference':case['expected']})
    fixture=json.loads((ARCHIVE/'native/frozen-before.json').read_text());queries=json.loads((ARCHIVE/'native/published-native-queries.json').read_text())
    native=execute_queries(queries,output/'published-native',name='published-linear-covariance',timeout=900)
    for key,expected in fixture['native_runtime'].items():
        if native[key]!=expected:raise ValueError('Published model reference runtime changed: '+key)
    fresh={r['key']:contract.clean(list(values(r))) for r in native['rows']}
    for case in native_cases():
        actual=fresh[case['key']];answer=case['expected'];unchanged=contract.equal(actual,case['published_native'])
        rows.append(comparison(case['key'],'unchanged-pinned-R-lm/vcov/car3.1-3-hccm',
            'every-model-coefficient-and-covariance-cell/no-extra-vote-for-derived-inference',actual,answer,
            unchanged and contract.equal(actual,answer),unchanged,'all-numeric-fields-atol-zero',1e-9,0.))
    (output/'linear-model-paired-data.json').write_text(json.dumps({'rows':paired},indent=2,allow_nan=False),encoding='utf-8')
    return rows
