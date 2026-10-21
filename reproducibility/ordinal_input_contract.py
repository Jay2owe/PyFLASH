"""Frozen response laws across input formats; no whole-estimator qualification."""
from copy import deepcopy
import gzip
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse

from reproducibility import ordinal_response_contract as response
from reproducibility.ordinal_input_adapter import KINDS, model_for, represent

ARCHIVE = Path(__file__).with_name('reference-sources') / 'ordinal-response/inputs-v1'
COMPLETE_CAPABILITIES = frozenset()
CAPABILITY_PREFIXES = {name: ('ordinal-input.',) for name in response.CAPABILITIES}


def cases():
    from reproducibility.compact_evidence import digest
    declaration = json.loads((ARCHIVE / 'declaration.json').read_text())
    for relative, expected in declaration['sources'].items():
        if digest(Path(__file__).parents[1] / relative) != expected:
            raise ValueError('Frozen ordinal input dependencies changed: ' + relative)
    response.check_identity()
    return declaration['cases']


def observe(request, originals):
    case = originals[request['case_key']]['case']
    mode, kind = request['mode'], request['container']
    model = model_for(case)
    if mode == 'responses':
        data = represent(case['x'], kind)
        before = deepcopy(data)
        actual = dict(predictions=model.predict(data).tolist(),
                      probabilities=model.predict_proba(data).tolist())
        if sparse.issparse(data):
            owned = (data != before).nnz == 0
        elif isinstance(data, pd.DataFrame):
            owned = data.equals(before)
        else:
            owned = np.array_equal(data, before)
        return dict(response=actual, input_unchanged=bool(owned))
    if mode == 'empty':
        data = represent(np.empty((0, len(case['coef']))), kind)
        return dict(prediction_shape=list(model.predict(data).shape),
                    probability_shape=list(model.predict_proba(data).shape))
    data = np.zeros((1, len(case['coef']) + (mode == 'wrong_features')))
    if mode == 'nonfinite':
        data[0, 0] = {'nan': np.nan, 'inf': np.inf, '-inf': -np.inf}[request['value']]
    try:
        getattr(model, request['method'])(represent(data, kind))
    except ValueError:
        return {'rejected_with_value_error': True}
    return {'rejected_with_value_error': False}


def expected(request, originals):
    row = originals[request['case_key']]
    if request['mode'] == 'responses':
        result = response.reference.report(row['case'])
        if not response.equal(result, row['expected']):
            raise ValueError('Independent original response answers changed')
        return dict(response=result, input_unchanged=True)
    if request['mode'] == 'empty':
        return dict(prediction_shape=[0], probability_shape=[0, len(row['case']['theta']) + 1])
    return {'rejected_with_value_error': True}


def validate(output):
    from reproducibility.normality_association_validation import comparison
    requests = cases()
    originals = {row['case']['key']: row for row in response.cases()}
    rows = []
    with gzip.open(output / 'ordinal-input-paired.jsonl.gz', 'xt', encoding='utf-8') as stream:
        for request in requests:
            actual = observe(request, originals)
            answer = expected(request, originals)
            agrees = response.equal(actual, answer)
            rows.append(comparison(request['key'], 'unchanged-500-digit-CDF-laws/finite-feature-input-protocol',
                'ordinal-response-inputs/no-new-independent-estimator-vote', actual, answer,
                agrees, True, 'all-predictions-probabilities-shapes-and-input-ownership', 1e-9, 0.))
            stream.write(json.dumps(dict(request=request, actual=actual, expected=answer,
                                         agrees=agrees), allow_nan=False) + '\n')
    return rows
