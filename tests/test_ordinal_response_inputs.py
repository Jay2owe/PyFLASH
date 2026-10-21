"""Input representations preserve frozen ordinal laws and reject invalid data."""
from copy import deepcopy

import numpy as np
import pandas as pd
import pytest
from scipy import sparse

from reproducibility import ordinal_response_contract as contract
from reproducibility.ordinal_input_adapter import KINDS, model_for, represent


@pytest.mark.parametrize('row', contract.cases(), ids=lambda row: row['case']['key'])
@pytest.mark.parametrize('kind', KINDS)
def test_representations_preserve_frozen_responses(row, kind):
    case = row['case']
    data = represent(case['x'], kind)
    before = deepcopy(data)
    model = model_for(case)
    expected = contract.reference.report(case)
    assert contract.equal(expected, row['expected'])
    assert contract.equal(model.predict(data).tolist(), expected['predictions'])
    assert contract.equal(model.predict_proba(data).tolist(), expected['probabilities'])
    if sparse.issparse(data):
        assert (data != before).nnz == 0
    elif isinstance(data, pd.DataFrame):
        pd.testing.assert_frame_equal(data, before)
    else:
        np.testing.assert_array_equal(data, before)


@pytest.mark.parametrize('method', ('predict', 'predict_proba'))
@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('value', (np.nan, np.inf, -np.inf))
def test_nonfinite_features_are_rejected(method, kind, value):
    case = contract.cases()[0]['case']
    values = np.zeros((1, len(case['coef'])))
    values[0, 0] = value
    with pytest.raises(ValueError):
        getattr(model_for(case), method)(represent(values, kind))


@pytest.mark.parametrize('kind', ('array', 'dataframe', 'csr', 'csc', 'coo'))
def test_empty_batch_keeps_output_shapes(kind):
    case = contract.cases()[0]['case']
    data = represent(np.empty((0, len(case['coef']))), kind)
    model = model_for(case)
    assert model.predict(data).shape == (0,)
    assert model.predict_proba(data).shape == (0, len(case['theta']) + 1)


@pytest.mark.parametrize('method', ('predict', 'predict_proba'))
@pytest.mark.parametrize('kind', KINDS)
def test_wrong_feature_count_is_rejected(method, kind):
    case = contract.cases()[0]['case']
    data = represent(np.zeros((2, len(case['coef']) + 1)), kind)
    with pytest.raises(ValueError):
        getattr(model_for(case), method)(data)
