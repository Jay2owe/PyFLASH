"""Complete normality references and literal association request contracts."""
import hashlib
import json
from pathlib import Path


def validate(output):
    from reproducibility import anderson_contract as normality
    from reproducibility import anderson_mathematical_reference as mathematics
    from reproducibility import association_specs_contract as requests
    from reproducibility.reference_runtime import values

    fixture = normality.check_identity()
    if hashlib.sha256(Path(mathematics.__file__).read_bytes()).hexdigest() != fixture['mathematical_reference_sha256']:
        raise ValueError('Independent normality mathematical source changed.')
    producer = normality.FIXTURE.parent.parent / fixture['producer_path']
    if hashlib.sha256(producer.read_bytes()).hexdigest() != fixture['producer_sha256']:
        raise ValueError('Original normality producer changed.')
    native = normality.execute(output / 'native-r-normality')
    for field in ['R', 'wasm_sha256']:
        if native[field] != fixture['native'][field]:
            raise ValueError('Normality native reference runtime changed.')
    native_rows = {row['key']: row for row in native['rows']}
    rows, paired = [], []
    for case in normality.cases():
        actual, expected = normality.production(case), normality.expected(case)
        answers = {'80-digit-independent-log-Gaussian-calibration': mathematics.mathematical(case)}
        if case['key'] in native_rows:
            answers['unchanged-published-nortest-1.0-3'] = list(values(native_rows[case['key']]))
        for name, answer in answers.items():
            unchanged = normality.equal(answer, expected)
            agrees = unchanged and normality.equal(actual, answer)
            rows.append(comparison(case['key'], name, 'independent-normality-statistic-and-calibration',
                                   actual, answer, agrees, unchanged, 'statistic-and-positive-probability/probability-atol-zero', 1e-9, 1e-12))
        paired.append({'case': case, 'production': actual, 'references': answers,
                       'frozen_reference': expected})
    (output / 'normality-paired-data.json').write_text(json.dumps({'rows': paired,
        'reference': fixture['reference'], 'probability_absolute_tolerance': 0.}, indent=2, allow_nan=False), encoding='utf-8')

    requests.check_identity()
    paired = []
    for case in requests.cases():
        actual, answer = requests.production(case), requests.expected(case)
        agrees = actual == answer
        rows.append(comparison(case['key'], 'literal-ordered-association-request-schema',
                               'functional-request-validation/no-scientific-fit-vote', actual, answer,
                               agrees, True, 'all-normalized-fields-or-typed-error', 0., 0.))
        paired.append({'case': case, 'production': actual, 'reference': answer, 'agrees': agrees})
    (output / 'association-request-paired-data.json').write_text(json.dumps({'rows': paired},
        indent=2, allow_nan=False), encoding='utf-8')
    return rows


def comparison(key, reference, family, actual, answer, agrees, unchanged, shape, rtol, atol):
    return {'contract': key, 'reference': reference, 'family': family,
            'status': 'agree' if agrees else 'disagree', 'shape': shape,
            'missingness_equal': agrees, 'max_absolute_error': '', 'rtol': rtol, 'atol': atol,
            'pyflash_nonfinite': 'explicit-null-undefinedness', 'frozen_reference_agrees': unchanged,
            'pyflash_values': json.dumps(actual), 'reference_values': json.dumps(answer)}
