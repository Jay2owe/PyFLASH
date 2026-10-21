"""Frozen independent answers catch numerical and missing-value regressions."""
import json
import numpy as np
import pytest
from reproducibility import extended
from reproducibility.cases import RTOL, ATOL

EXPECTED = json.loads(extended.FIXTURE.read_text(encoding="utf-8"))
LINEAR = json.loads(extended.LINEAR_FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def actual():
    return extended.pyflash_values()


@pytest.mark.parametrize("row", EXPECTED["rows"]+LINEAR["rows"], ids=lambda row: row[0]+"/"+row[1])
def test_extended_scientific_contract(row, actual):
    name, reference, family, values = row
    expected = np.asarray([np.nan if v is None else v for v in values], float)
    observed = np.asarray(actual[name], float)
    assert observed.shape == expected.shape
    assert np.array_equal(np.isnan(observed), np.isnan(expected)), name
    np.testing.assert_allclose(observed, expected, rtol=RTOL, atol=ATOL,
                               err_msg=f"{name}: {reference} ({family})")


def test_frozen_extended_input_identity():
    assert extended.inputs() == EXPECTED["inputs"]


def test_changed_prediction_and_missing_coordinate_fail():
    values = next(row[3] for row in EXPECTED["rows"] if row[0] == "growth.linear.noisy")
    original = np.asarray(values, float)
    changed = original.copy()
    changed[-1] += .01
    with pytest.raises(AssertionError):
        np.testing.assert_allclose(changed, original, rtol=RTOL, atol=ATOL)
    missing = next(row[3] for row in EXPECTED["rows"] if row[0] == "mad.4")
    observed = np.asarray([np.nan if v is None else v for v in missing])
    observed[-1] = np.inf
    assert not np.array_equal(np.isnan(observed), np.array([v is None for v in missing]))


def test_group_outlier_flags_ignore_infinite_observations():
    import pandas as pd
    from PyFLASH.stats_extra import flag_outliers
    frame = pd.DataFrame({"value": [1., 2., 3., 4., 5., 30., np.inf, -np.inf]})
    result = flag_outliers(frame, ["value"], methods=("iqr", "mad"))
    assert result["row"].tolist() == [5]
    assert result["iqr_outlier"].tolist() == [True]
    assert result["mad_outlier"].tolist() == [True]
