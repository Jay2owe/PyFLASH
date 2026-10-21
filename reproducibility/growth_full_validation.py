"""Recalculate full fit answers with independent rational and 70-digit kernels."""
import hashlib
import json
import math
from pathlib import Path


def validate(output):
    from reproducibility import growth_contract as contract
    from reproducibility import growth_linear_mathematical_reference as linear
    from reproducibility import growth_boundary_mathematical_reference as nonlinear
    from reproducibility.normality_association_validation import comparison
    fixture = contract.check_identity()
    for name, sha in fixture['mathematical_modules'].items():
        if hashlib.sha256((contract.FIXTURE.parent.parent/name).read_bytes()).hexdigest() != sha:
            raise ValueError('Growth mathematical reference changed.')
    cache, selected = {}, {}
    for row in fixture['rows']:
        case, answer = row['case'], row['expected']
        if case['parameters']['model'] != 'auto' and 'error_type' not in answer:
            selected[(input_identity(case), answer['model'])] = answer

    def calculate(case, model):
        identity = input_identity(case)
        key = identity, model
        if key not in cache:
            p = case['parameters']
            xx, yy = finite_pairs(p)
            if model == 'linear':
                cache[key] = linear.reference({'parameters':{'x':xx, 'y':yy, 'prediction_x':p['prediction_x']}})
            else:
                seed = selected[key]
                initial = [v['value'] for v in seed['params'].values()]
                fixed = None
                fixed_midpoint = None
                if model == 'logistic' and initial[-1] in [.1,10]:
                    fixed = initial[-1]
                if model == 'logistic' and initial[2] == 1e-9:
                    fixed_midpoint = initial[2]
                cache[key] = nonlinear.fit(xx, yy, p['prediction_x'], model, initial, fixed, fixed_midpoint)
        return cache[key]

    rows, pairs = [], []
    for recorded in fixture['rows']:
        case, expected = recorded['case'], recorded['expected']
        actual = contract.production(case)
        if 'error_type' in expected:
            # These cases are the explicit positive-domain condition; no fitting
            # implementation supplies a scientific result for them.
            xx, _ = finite_pairs(case['parameters'])
            if case['parameters']['model'] != 'logistic' or min(xx)>0:
                raise ValueError('Undefined growth case lacks its independent domain witness.')
            answer = {'error_type':'ValueError'}
        elif case['parameters']['model'] == 'auto':
            candidates = {model: calculate(case,model) for model in expected['all_models']}
            winner = min(candidates, key=lambda model:candidates[model]['aic'])
            answer = json.loads(json.dumps(candidates[winner]))
            answer['all_models'] = {model:{'aic':a['aic']} for model,a in candidates.items()}
        else:
            answer = calculate(case, case['parameters']['model'])
        unchanged = contract.equal(answer, expected)
        agrees = unchanged and contract.equal(actual,answer)
        rows.append(comparison(case['key'], 'fresh-exact-rational-or-70-digit-stationary-full-fit',
            'independent-objective-derivatives-covariance-and-candidate-scores', actual, answer,
            agrees, unchanged, 'complete-parameters-errors-predictions-and-all-candidate-scores', 1e-9, 1e-12))
        pairs.append({'case':case, 'production':actual, 'mathematical_reference':answer,
                      'frozen_reference':expected, 'agrees':agrees})
    (output/'growth-full-paired-data.json').write_text(json.dumps({'rows':pairs,
        'reference_rule':fixture['reference'], 'boundary_rule':fixture['boundary_reference_rule'],
        'source_manifest':fixture['source_manifest']},indent=2,allow_nan=False),encoding='utf-8')
    return rows


def finite_pairs(parameters):
    pairs=sorted((float(x),float(y)) for x,y in zip(parameters['x'],parameters['y'])
                 if x is not None and y is not None and math.isfinite(float(x)) and math.isfinite(float(y)))
    return [x for x,y in pairs],[y for x,y in pairs]


def input_identity(case):
    xx,yy=finite_pairs(case['parameters'])
    return json.dumps([xx,yy,case['parameters']['prediction_x']],sort_keys=True)
