"""Fresh independent full reports, published kernels and direct small-tail events."""
from pathlib import Path
import json,math
import mpmath as mp
from reproducibility import one_way_contract as contract
from reproducibility import one_way_report_reference as reference
from reproducibility.normality_association_validation import comparison
from reproducibility.reference_runtime import execute_queries,values
ARCHIVE=Path(__file__).with_name('reference-sources')/'one-way'
NATIVE=Path(__file__).with_name('fixtures')/'one_way_native_reference.json'

def native_cases():return json.loads(NATIVE.read_text())['rows']
def range_cases():return json.loads((ARCHIVE/'range-before/frozen-before.json').read_text())['rows']
def helper_cases():return json.loads((ARCHIVE/'helper-tails/frozen-before.json').read_text())['rows']

SIDAK_REQUEST_BOUNDARY=NATIVE.parent/'sidak_tail_request_boundary_v2.json'
SIDAK_REQUEST_BOUNDARY_SHA256='e5632b44d71063b6973de3a39ac7f0ce6601e5e83081f444f2b716d50963db18'

def helper_response(case):
    """Retain historical arithmetic separately from invalid-request refusal."""
    import hashlib
    original=ARCHIVE/'helper-tails/frozen-before.json'
    if hashlib.sha256(SIDAK_REQUEST_BOUNDARY.read_bytes()).hexdigest()!=SIDAK_REQUEST_BOUNDARY_SHA256:
        raise ValueError('Versioned Sidak request boundary changed.')
    fixture=json.loads(SIDAK_REQUEST_BOUNDARY.read_text())
    if hashlib.sha256(original.read_bytes()).hexdigest()!=fixture['original_sha256']:
        raise ValueError('Historical Sidak tail evidence changed.')
    if [row['original_case'] for row in fixture['rows']]!=helper_cases():
        raise ValueError('Original Sidak tail inputs or arithmetic answers changed.')
    row=next(row for row in fixture['rows'] if row['original_case']['key']==case['key'])
    if row['original_case']!=case:
        raise ValueError('Sidak tail request differs from the preserved original.')
    return row['public_response']

def helper_production(case):
    from PyFLASH import stats
    p=case['parameters']
    try:return contract.clean(stats.sidak_correction(float(p['p_value']),p['n_tests']))
    except Exception as error:return {'error':type(error).__name__}
def range_queries():return json.loads((ARCHIVE/'range-inputs/one-way-exact-geometry-range-queries.json').read_text())

def required_keys():
    from reproducibility.anova_native_field_validation import cases
    from reproducibility.extreme_inference_contract import required_keys as extreme_keys
    return {r['key'] for r in contract.cases()}|{r['query']['key'] for r in native_cases() if r['role']=='independent-native-corroboration'}|{r['key'] for r in range_cases()}|{r['key'] for r in range_queries()}|{r['query']['key'] for r in cases('ordinary') if r['role']=='independent-native-corroboration'}|extreme_keys('ordinary')

def check_runtime(actual,expected):
    for key,value in expected.items():
        if actual[key]!=value:raise ValueError('Native one-way runtime changed: '+key)

def high_precision_range(p):
    with mp.workdps(80):
        q=mp.mpf(p['threshold']);count=p['count'];degrees=mp.mpf(p['degrees'])
        if count==2:
            return float(mp.erfc(q/2) if mp.isinf(degrees) else mp.betainc(degrees/2,mp.mpf('.5'),0,degrees/(degrees+q*q/2),regularized=True))
        def integrand(offset):
            z=offset-q/2;base=mp.erfc(z/mp.sqrt(2))/2;other=mp.erfc((z+q)/mp.sqrt(2))/2
            if not base:return mp.mpf(0)
            ratio=other/base;union=mp.mpf(1) if ratio==1 else -mp.expm1((count-1)*mp.log1p(-ratio))
            return count*mp.exp(-z*z/2+q*q/4)/mp.sqrt(2*mp.pi)*base**(count-1)*union
        return float(mp.quad(integrand,[-mp.inf,-15,-8,-4,0,4,8,15,mp.inf])*mp.exp(-q*q/4))

def validate(output):
    contract.check_identity();rows=[];paired=[];diagnostics=[]
    queries=range_queries();native=execute_queries(queries,output/'direct-range-geometry',name='one-way-range-geometry',timeout=900)
    check_runtime(native,reference.inputs['native_identity'])
    fresh={r['key']:values(r)[0] for r in native['rows']}
    for query in queries:
        actual=fresh[query['key']];expected=reference.inputs['range_probabilities'][query['key']]
        agrees=math.isclose(actual,expected,rel_tol=1e-9,abs_tol=0.)
        rows.append(comparison(query['key'],'direct-minimum-Gaussian-event/chi-scale-integration',
            'one-way-common-range-input/no-additional-published-kernel-vote',actual,expected,agrees,True,'probability-atol-zero',1e-9,0.))
    previous=reference.range_values
    try:
        reference.range_values=fresh
        for case in contract.cases():
            from reproducibility.reported_posthoc_statistic_reference import expected_report
            actual=contract.production(case);answer=expected_report(case,reference.report(case))
            unchanged=contract.equal(answer,case['expected']);agrees=unchanged and contract.equal(actual,answer)
            rows.append(comparison(case['key'],'exact-binary-geometry/80-digit-beta-inference/independent-range-inputs',
                'complete-one-way-report',actual,answer,agrees,unchanged,'all-fields/probability-atol-zero',1e-9,1e-12))
            paired.append({'case':case,'production':actual,'reference':answer,'frozen_reference':case['expected']})
    finally:reference.range_values=previous
    fixture=json.loads(NATIVE.read_text());native=execute_queries([r['query'] for r in fixture['rows']],output/'published-r-kernels',name='one-way-published-kernels',timeout=900)
    check_runtime(native,fixture['native_runtime']);observed={r['key']:values(r) for r in native['rows']}
    for case in fixture['rows']:
        actual=contract.clean(observed[case['query']['key']]);expected=case['expected']
        if case['role']!='independent-native-corroboration':
            diagnostics.append({'case':case,'native':actual});continue
        agrees=len(actual)==len(expected) and all(contract.equal(a,b,('pvalues',) if i else ()) for i,(a,b) in enumerate(zip(actual,expected)))
        rows.append(comparison(case['query']['key'],'unchanged-R-stats-and-pinned-PMCMRplus',
            'native-one-way-corroboration/common-unit-scaled-inputs/no-extra-engine-vote',actual,expected,agrees,True,'F-probabilities/probability-atol-zero',1e-9,1e-12))
    queries=json.loads((ARCHIVE/'range-before/direct-range-tails-queries.json').read_text())
    native=execute_queries(queries,output/'direct-tail-witnesses',name='studentized-range-direct-tails',timeout=900)
    check_runtime(native,reference.inputs['native_identity']);observed={r['key']:values(r) for r in native['rows']}
    from PyFLASH._studentized_range import range_tail
    for case in range_cases():
        p=case['parameters'];actual=range_tail(p['threshold'],p['count'],float(p['degrees']));answer,published=observed[case['key']]
        unchanged=math.isclose(answer,case['expected'],rel_tol=1e-9,abs_tol=0.);agrees=unchanged and math.isclose(actual,answer,rel_tol=1e-9,abs_tol=0.)
        rows.append(comparison(case['key'],'independent-direct-range-event/chi-mixture',
            'complete-parent-range-tail-dependency/no-new-published-kernel-vote',actual,answer,agrees,unchanged,'probability-atol-zero',1e-9,0.))
        diagnostics.append({'key':case['key'],'published_R_ptukey':published,'mathematical_reference':answer})
        if p['count']==2 or float(p['degrees'])==math.inf:
            witness=high_precision_range(p);agrees=math.isclose(answer,witness,rel_tol=1e-9,abs_tol=0.)
            rows.append(comparison('range-80-digit.'+case['key'],'80-digit-beta-or-normalized-Gaussian-range-quadrature',
                'mathematical-convergence-witness/no-extra-published-kernel-vote',answer,witness,agrees,True,'probability-atol-zero',1e-9,0.))
    from PyFLASH import stats
    for case in helper_cases():
        p=case['parameters'];probability=float(p['p_value']);count=p['n_tests']
        if not math.isfinite(probability):
            actual=helper_production(case);answer=helper_response(case)
            diagnostics.append({'key':case['key'],'historical_arithmetic':case['expected'],
                'current_public_response':actual,'classification':'invalid-domain-refusal/no-numerical-agreement-vote'})
            rows.append(comparison(case['key'],'literal-finite-scalar-request-contract',
                'functional-invalid-request-refusal/no-numerical-vote',actual,answer,actual==answer,True,
                'exact-exception-type; original-undefined-arithmetic-retained',0.,0.))
            continue
        with mp.workdps(80):
            answer=1. if probability==1 else float(-mp.expm1(count*mp.log1p(-mp.mpf(probability))))
        actual=contract.clean(stats.sidak_correction(probability,count));answer=contract.clean(answer)
        unchanged=contract.equal(answer,case['expected'],('pvalues',));agrees=unchanged and contract.equal(actual,answer,('pvalues',))
        rows.append(comparison(case['key'],'80-digit-direct-Sidak-tail',
            'scalar-valid-count-tail-subcontract/request-domain-still-separate',actual,answer,agrees,unchanged,'probability-atol-zero',1e-9,0.))
    from reproducibility.anova_native_field_validation import validate as validate_fields
    rows.extend(validate_fields('ordinary',output/'published-real-statistic-fields'))
    (output/'one-way-paired-data.json').write_text(json.dumps({'rows':paired,'native_diagnostics':contract.clean(diagnostics),
        'probability_absolute_tolerance':0.},indent=2,allow_nan=False),encoding='utf-8')
    return rows
