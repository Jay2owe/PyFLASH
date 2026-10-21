"""Fresh complete slope equations and native QR fits with immutable paired arrays."""
import json
from reproducibility import interaction_slope_contract as contract
from reproducibility import interaction_slope_mathematical_reference as mathematical
from reproducibility.normality_association_validation import comparison
from reproducibility.reference_runtime import execute_queries,values

def validate(output):
    fixture=contract.check_identity()
    native=execute_queries(fixture['native_queries'],output/'native-r-interaction-slope',
                           name='complete-slope-QR-and-equivalent-units',timeout=600)
    for field,expected in fixture['native_identity'].items():
        if native[field]!=expected:raise ValueError('Slope native runtime identity changed: '+field)
    native_rows={row['key']:row for row in native['rows']}
    fields=['p','estimate','se','t','df','n','slope_reference','slope_other']
    rows,paired=[],[]
    for case in contract.cases():
        actual=contract.production(case);frozen=contract.expected(case)
        answer=contract.clean(mathematical.reference(case['parameters']))
        unchanged=contract.equal(answer,frozen);agrees=unchanged and contract.equal(actual,answer)
        rows.append(comparison(case['key'],'exact-rational-identifiability-and-70-digit-slope-coefficients-covariance-Student-tails',
            'independent-complete-least-squares-equations/paired-finite-observations',actual,answer,agrees,unchanged,
            'all-ten-fields-or-typed-invalid-request/p-atol-zero',1e-9,1e-12))
        answers={'mathematical':answer}
        if case['key'] in native_rows:
            numbers=contract.clean(values(native_rows[case['key']]))
            native_answer={**{key:answer[key] for key in ['reference','other']},**dict(zip(fields,numbers,strict=True))}
            unchanged=contract.equal(native_answer,frozen);agrees=unchanged and contract.equal(actual,native_answer)
            rows.append(comparison(case['key'],'native-R-QR-lm-fit-and-exact-equivalent-unit-transforms',
                'published-native-linear-solver/shared-R-runtime/no-extra-unit-transform-vote',
                actual,native_answer,agrees,unchanged,'all-fit-fields/reference-identities-literal/p-atol-zero',1e-9,1e-12))
            answers['native']=native_answer
        paired.append({'case':case,'production':actual,'references':answers,'frozen_reference':frozen})
    (output/'interaction-slope-paired-data.json').write_text(json.dumps({'rows':paired,
        'scope':fixture['scope'],'reference':fixture['reference'],'probability_absolute_tolerance':0.},indent=2,allow_nan=False),encoding='utf-8')
    return rows
