"""Fresh independent categorical projections, every matrix cell and native fields."""
from pathlib import Path
import json,math
from reproducibility import two_way_contract as contract,two_way_mathematical_reference as reference,two_way_matrix_reference as matrices
from reproducibility.normality_association_validation import comparison
from reproducibility.reference_runtime import execute_queries,values
ARCHIVE=Path(__file__).with_name('reference-sources')/'two-way-reports'

def queries():return json.loads((ARCHIVE/'inputs/two-way-condition-range-queries.json').read_text())
def native_cases():return json.loads((ARCHIVE/'native/frozen-before.json').read_text())['rows']
def required_keys():
    return {r['key'] for r in contract.cases()+contract.matrix_cases()}|{r['key'] for r in queries()}|{r['query']['key'] for r in native_cases() if r['role']=='independent-native-corroboration'}

def native_equal(actual,expected):
    pindices={7,8,9,10}|{i for i in range(15,len(expected)) if (i-15)%2==1}
    return len(actual)==len(expected) and all(a==b if isinstance(b,str) else isinstance(a,(int,float)) and math.isclose(a,b,rel_tol=1e-9,abs_tol=0. if i in pindices else 1e-12) for i,(a,b) in enumerate(zip(actual,expected)))

def validate(output):
    contract.check_identity();rows=[];paired=[]
    native=execute_queries(queries(),output/'direct-range-geometry',name='two-way-condition-range',timeout=900)
    for key,expected in reference.inputs_data['native_runtime'].items():
        if native[key]!=expected:raise ValueError('Two-factor range runtime changed: '+key)
    fresh={r['key']:values(r)[0] for r in native['rows']}
    for query in queries():
        actual=fresh[query['key']];answer=reference.inputs_data['range_probabilities'][query['key']]
        agrees=math.isclose(actual,answer,rel_tol=1e-9,abs_tol=0.)
        rows.append(comparison(query['key'],'direct-minimum-Gaussian-event/chi-scale-integration',
            'condition-range-common-input/no-additional-published-kernel-vote',actual,answer,agrees,True,'probability-atol-zero',1e-9,0.))
    previous=reference.RANGE
    try:
        reference.RANGE=fresh
        for case in contract.cases()+contract.matrix_cases():
            actual=contract.production(case);answer=matrices.reference(case) if case['key'].startswith('two-way-tukey-matrix.') else reference.report(case)
            unchanged=contract.equal(answer,case['expected']);agrees=unchanged and contract.equal(actual,answer)
            rows.append(comparison(case['key'],'exact-rational-hierarchical-projections/80-digit-beta-tails/independent-range-inputs',
                'complete-two-factor-report-or-every-Tukey-matrix-cell',actual,answer,agrees,unchanged,'all-numeric-fields-atol-zero',1e-9,0.))
            paired.append({'case':case,'production':actual,'reference':answer,'frozen_reference':case['expected']})
    finally:reference.RANGE=previous
    fixture=json.loads((ARCHIVE/'native/frozen-before.json').read_text());native_queries=json.loads((ARCHIVE/'native/two-way-published-native-queries.json').read_text())
    native=execute_queries(native_queries,output/'published-native-fields',name='two-way-published-fields',timeout=900)
    for key,expected in fixture['native_runtime'].items():
        if native[key]!=expected:raise ValueError('Published two-factor native runtime changed: '+key)
    fresh={r['key']:contract.clean(list(values(r))) for r in native['rows']};diagnostics=[]
    for case in native_cases():
        key=case['query']['key'];actual=fresh[key];answer=case['expected'];unchanged=native_equal(actual,case['published_native'])
        if case['role']=='retained-native-diagnostic':
            if not unchanged:raise ValueError('Two-factor native diagnostic changed: '+key)
            diagnostics.append({**case,'fresh_published_native':actual});continue
        agrees=unchanged and native_equal(actual,answer)
        rows.append(comparison(key,'unchanged-pinned-R-stats-lm/nested-anova/TukeyHSD',
            'published-two-factor-fit-and-condition-posthoc-fields',actual,answer,agrees,unchanged,'all-fields/probability-atol-zero',1e-9,1e-12))
    (output/'two-way-native-diagnostics.json').write_text(json.dumps({'rows':diagnostics},indent=2,allow_nan=False),encoding='utf-8')
    (output/'two-way-paired-data.json').write_text(json.dumps({'rows':paired,'numeric_absolute_tolerance':0.},indent=2,allow_nan=False),encoding='utf-8')
    return rows
