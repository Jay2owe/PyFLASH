"""Fresh exact weighted reports, direct range probabilities and native fields."""
from pathlib import Path
import json,math
from reproducibility import welch_one_way_contract as contract
from reproducibility import welch_one_way_report_reference as reference
from reproducibility import anova_native_field_validation as native_fields
from reproducibility.normality_association_validation import comparison
from reproducibility.reference_runtime import execute_queries,values
ARCHIVE=Path(__file__).with_name('reference-sources')/'anova-reports/welch-range-inputs'

def queries():return json.loads((ARCHIVE/'welch-exact-geometry-range-queries.json').read_text())
def required_keys():
    from reproducibility.extreme_inference_contract import required_keys as extreme_keys
    return {r['key'] for r in contract.cases()}|{r['key'] for r in queries()}|{r['query']['key'] for r in native_fields.cases('welch') if r['role']=='independent-native-corroboration'}|extreme_keys('welch')

def validate(output):
    contract.check_identity();rows=[];paired=[]
    native=execute_queries(queries(),output/'direct-range-geometry',name='welch-range-geometry',timeout=900)
    for key,expected in reference.inputs['native_runtime'].items():
        if native[key]!=expected:raise ValueError('Native unequal-variance range runtime changed: '+key)
    fresh={r['key']:values(r)[0] for r in native['rows']}
    for query in queries():
        actual=fresh[query['key']];expected=reference.inputs['range_probabilities'][query['key']]
        agrees=math.isclose(actual,expected,rel_tol=1e-9,abs_tol=0.)
        rows.append(comparison(query['key'],'direct-minimum-Gaussian-event/chi-scale-integration',
            'unequal-variance-common-range-input/no-additional-published-kernel-vote',actual,expected,agrees,True,'probability-atol-zero',1e-9,0.))
    previous=reference.inputs['range_probabilities']
    try:
        reference.inputs['range_probabilities']=fresh
        for case in contract.cases():
            actual=contract.production(case);answer=reference.report(case)
            unchanged=contract.equal(answer,case['expected']);agrees=unchanged and contract.equal(actual,answer)
            rows.append(comparison(case['key'],'exact-binary-weighted-geometry/80-digit-beta-tails/independent-range-inputs',
                'complete-unequal-variance-ANOVA-report',actual,answer,agrees,unchanged,'all-fields/probability-atol-zero',1e-9,1e-12))
            paired.append({'case':case,'production':actual,'reference':answer,'frozen_reference':case['expected']})
    finally:reference.inputs['range_probabilities']=previous
    rows.extend(native_fields.validate('welch',output/'published-real-statistic-fields'))
    (output/'welch-one-way-paired-data.json').write_text(json.dumps({'rows':paired,'probability_absolute_tolerance':0.},indent=2,allow_nan=False),encoding='utf-8')
    return rows
