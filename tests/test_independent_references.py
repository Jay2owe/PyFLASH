"""Frozen independently generated values exercise production numerical APIs."""
import numpy as np
import pytest

from reproducibility.cases import ATOL, RTOL, inputs, load_expected
from reproducibility.comparisons import pyflash_values


@pytest.fixture(scope="module")
def actual():
    return pyflash_values()


@pytest.mark.parametrize("row",load_expected()["rows"],ids=lambda row:row[0]+"/"+row[1])
def test_numerical_contract_matches_frozen_independent_reference(row,actual):
    contract,reference,family,values = row
    expected = np.asarray([np.nan if v is None else v for v in values],float)
    observed = np.asarray(actual[contract],float)
    assert observed.shape == expected.shape
    assert np.array_equal(np.isnan(observed),np.isnan(expected))
    np.testing.assert_allclose(observed,expected,rtol=RTOL,atol=ATOL,
                               err_msg=f"{contract}: {reference} ({family})")


def test_fixture_inputs_are_identical():
    assert inputs() == load_expected()["inputs"]


def test_references_detect_corrupted_statistic_and_array():
    expected = load_expected()["rows"]
    for contract in ("ttest.welch.balanced","correction.fdr_bh","cosinor.fixed_sparse"):
        values = next(row[3] for row in expected if row[0] == contract)
        original = np.asarray([np.nan if v is None else v for v in values],float)
        changed = original.copy()
        changed[0] += .01
        with pytest.raises(AssertionError):
            np.testing.assert_allclose(changed,original,rtol=RTOL,atol=ATOL)
