"""Fresh full rank reports, direct range integrals and unchanged published fields."""
from pathlib import Path
import json,math
from reproducibility import rank_contract as contract,rank_report_reference as reference
from reproducibility.normality_association_validation import comparison
from reproducibility.reference_runtime import execute_queries,values
ARCHIVE=Path(__file__).with_name('reference-sources')/'rank-reports'

def queries():return json.loads((ARCHIVE/'inputs/rank-direct-range-queries.json').read_text())
def native_cases():return json.loads((ARCHIVE/'native/frozen-before.json').read_text())['rows']
def required_keys():
    return {r['key'] for r in contract.cases()}|{r['key'] for r in queries()}|{r['query']['key'] for r in native_cases() if r['role']=='independent-native-corroboration'}

def native_equal(actual,expected):
    return len(actual)==len(expected) and all(a==b if isinstance(b,str) else isinstance(a,(int,float)) and math.isclose(a,b,rel_tol=1e-9,abs_tol=0. if i%2 else 1e-12) for i,(a,b) in enumerate(zip(actual,expected)))

def validate(output):
    contract.check_identity();rows=[];paired=[]
    native=execute_queries(queries(),output/'direct-range-geometry',name='rank-range-geometry',timeout=900)
    for key,expected in reference.inputs['native_runtime'].items():
        if native[key]!=expected:raise ValueError('Native rank range runtime changed: '+key)
    fresh={r['key']:values(r)[0] for r in native['rows']}
    for query in queries():
        actual=fresh[query['key']];answer=reference.inputs['range_probabilities'][query['key']]
        agrees=math.isclose(actual,answer,rel_tol=1e-9,abs_tol=0.)
        rows.append(comparison(query['key'],'direct-minimum-Gaussian-event-integration',
            'rank-range-common-input/no-additional-published-kernel-vote',actual,answer,agrees,True,'positive-probability-atol-zero',1e-9,0.))
    previous=reference.RANGE
    try:
        reference.RANGE=fresh
        for case in contract.cases():
            actual=contract.production(case);answer=reference.report(case)
            unchanged=contract.equal(answer,case['expected']);agrees=unchanged and contract.equal(actual,answer)
            rows.append(comparison(case['key'],'exact-rational-midranks/80-digit-tails/accepted-null-and-correction-composition',
                'complete-rank-group-report',actual,answer,agrees,unchanged,'all-fields/probability-atol-zero',1e-9,1e-12))
            paired.append({'case':case,'production':actual,'reference':answer,'frozen_reference':case['expected']})
    finally:reference.RANGE=previous
    native_fixture=json.loads((ARCHIVE/'native/frozen-before.json').read_text())
    native_queries=json.loads((ARCHIVE/'native/rank-published-native-queries.json').read_text())
    native=execute_queries(native_queries,output/'published-native-fields',name='rank-published-fields',timeout=900)
    for key,expected in native_fixture['native_runtime'].items():
        if native[key]!=expected:raise ValueError('Published rank kernel runtime changed: '+key)
    fresh={r['key']:contract.clean(list(values(r))) for r in native['rows']};diagnostics=[]
    for case in native_cases():
        key=case['query']['key'];answer=case['expected'];actual=fresh[key]
        unchanged=native_equal(actual,case['published_native'])
        if case['role']=='retained-native-diagnostic':
            if not unchanged:raise ValueError('Retained rank native diagnostic changed: '+key)
            diagnostics.append({**case,'fresh_published_native':actual});continue
        agrees=unchanged and native_equal(actual,answer)
        rows.append(comparison(key,'unchanged-pinned-PMCMRplus/rank-test-and-base-R',
            'published-rank-statistic-and-probability-fields',actual,answer,agrees,unchanged,'all-fields/probability-atol-zero',1e-9,1e-12))
    (output/'rank-native-diagnostics.json').write_text(json.dumps({'rows':diagnostics},indent=2,allow_nan=False),encoding='utf-8')
    (output/'rank-paired-data.json').write_text(json.dumps({'rows':paired,'probability_absolute_tolerance':0.},indent=2,allow_nan=False),encoding='utf-8')
    return rows
