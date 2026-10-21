"""Fresh native reference reports plus exact-unit invariance, with retained pairs."""
from pathlib import Path
import json
from reproducibility import dunnett_contract as contract
from reproducibility import finite_scale_contract as scale
from reproducibility.normality_association_validation import comparison
from reproducibility.reference_runtime import execute_queries, values

def validate(output):
    fixture=contract.check_identity()
    native=execute_queries(fixture['native_queries'], output/'native-r-dunnett',
                           name='complete-control-reports', timeout=1200)
    for field, expected in fixture['native_identity'].items():
        if native[field]!=expected:
            raise ValueError('Dunnett independent native runtime identity changed: '+field)
    native_rows={row['key']:row for row in native['rows']}
    rows,paired=[],[]
    for case in contract.cases():
        actual=contract.production(case);expected=contract.expected(case)
        numbers=values(native_rows[case['native_key']]);count=len(expected['rows'])
        answer={'columns':expected['columns'], 'rows':[
            [row[0],*contract.clean([numbers[index],numbers[count+index]])]
            for index,row in enumerate(expected['rows'])]}
        unchanged=contract.equal(answer,expected)
        agrees=unchanged and contract.equal(actual,answer)
        rows.append(comparison(case['key'],'native-R-deterministic-common-control-multivariate-Student-integrals',
            'independent-native-equations/shared-R-runtime/no-additional-quadrature-vote',
            actual,answer,agrees,unchanged,'all-ordered-comparison-statistic-and-p-value-fields/p-atol-zero',1e-9,1e-12))
        paired.append({'case':case,'production':actual,'reference':answer,'frozen_reference':expected})
    (output/'dunnett-paired-data.json').write_text(json.dumps({'rows':paired,
        'reference':fixture['reference'],'probability_absolute_tolerance':0.},indent=2,allow_nan=False),encoding='utf-8')
    scale.check_identity()
    pairs=[]
    from reproducibility import scalar_contracts,bootstrap_reference
    for case in scale.cases():
        actual=scale.production(case)
        if case['method'] in {'cohens_d','hedges_g'}:
            answer=scale.clean(scalar_contracts.reference({'capability':'PyFLASH.stats_extra.'+case['method'],
                                                          'parameters':case['parameters']})[0])
        elif case['method']=='effect_ci':
            p=case['parameters'];a,b=case['unscaled_groups'][:2]
            answer=bootstrap_reference.interval(a,b,p['eftype'],p['confidence'],case['draws'])
        else:
            numbers=values(native_rows[case['native_key']]);count=len(case['expected']['rows'])
            answer={'columns':case['expected']['columns'],'rows':[
                [row[0],*contract.clean([numbers[index],numbers[count+index]])]
                for index,row in enumerate(case['expected']['rows'])]}
        unchanged=scale.equal(answer,case['expected']);agrees=unchanged and scale.equal(actual,answer)
        rows.append(comparison(case['key'],'independent-raw-unit-scalar-equations-and-accepted-unit-invariant-reference',
            'exact-binary-unit-invariance/no-additional-independent-implementation-vote',
            actual,answer,agrees,unchanged,'complete-dimensionless-fields/common-recorded-bootstrap-draws',1e-9,1e-12))
        pairs.append({'case':case,'production':actual,'reference':answer,'frozen_reference':case['expected']})
    (output/'finite-scale-paired-data.json').write_text(json.dumps({'rows':pairs},indent=2,allow_nan=False),encoding='utf-8')
    return rows
