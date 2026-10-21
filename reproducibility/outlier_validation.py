"""Fresh native and high-precision outlier arrays plus full report composition."""
import json
from reproducibility import outlier_contract as contract
from reproducibility import rout_mathematical_reference as numeric
from reproducibility import outlier_report_mathematical_reference as report
from reproducibility.reference_runtime import execute_queries,values
from reproducibility.normality_association_validation import comparison


def validate(output):
    fixtures=contract.check_identity()
    native=execute_queries(fixtures['rout']['queries'],output/'native-r-outliers',
                           name='declared-constant-fit-full-outlier-fields')
    for field in ['R','wasm_sha256']:
        if native[field]!=fixtures['rout']['native'][field]:
            raise ValueError('Outlier native reference runtime changed.')
    native_rows={row['key']:row for row in native['rows']}
    rows,paired=[],[]
    for case in contract.cases():
        actual=contract.production(case);expected=contract.expected(case)
        if contract.kind(case)=='rout':
            mathematical=numeric.reference(case)
            raw=values(native_rows[case['key']]);size=len(case['parameters']['values'])
            native_answer=[[bool(v) for v in raw[:size]],
                *[contract.clean(raw[i*size:(i+1)*size]) for i in [1,2,3]],
                *contract.clean(raw[4*size:])]
            answers={'70-digit-declared-constant-IRLS-and-student-tail':mathematical,
                     'independent-native-R-declared-constant-variant':native_answer}
            family='independent-declared-outlier-mathematics/not-Prism-nonlinear-ROUT-equivalence'
        else:
            answers={'independent-literal-grouping-quantile-MAD-and-frozen-child-equations':report.reference(case)}
            family='complete-parent-report-composition/no-additional-child-implementation-vote'
        for name,answer in answers.items():
            unchanged=contract.equal(case,answer,expected)
            agrees=unchanged and contract.equal(case,actual,answer)
            rows.append(comparison(case['key'],name,family,actual,answer,agrees,unchanged,
                'all-aligned-outlier-fields-or-complete-ordered-report/probability-atol-zero',1e-9,1e-12))
        paired.append({'case':case,'production':actual,'references':answers,'frozen_reference':expected})
    (output/'outlier-paired-data.json').write_text(json.dumps({'rows':paired,
        'numeric_scope':fixtures['rout']['scope'],'report_scope':fixtures['report']['scope'],
        'probability_absolute_tolerance':0.},indent=2,allow_nan=False),encoding='utf-8')
    return rows
