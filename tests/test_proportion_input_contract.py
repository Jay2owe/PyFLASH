"""Invalid contingency counts must never silently select or truncate a test."""
import numpy as np
import pytest
from PyFLASH.stats_extra import proportion_test


@pytest.mark.parametrize('table', [
    [[1.5,2],[3,4]], [[-1,2],[3,4]], [[np.nan,2],[3,4]],
    [[np.inf,2],[3,4]], [[0,0],[3,4]], [[0,2],[0,4]],
    [[0,0],[0,0]], [[1,2]],
])
@pytest.mark.parametrize('force', [None,'chi2','fisher'])
def test_invalid_counts_raise_before_any_statistical_result(table,force):
    with pytest.raises(ValueError):
        proportion_test(table,force)


@pytest.mark.parametrize('force', ['fishre','FISHER','chi-square',''])
def test_unknown_method_does_not_silently_run_chi_square(force):
    with pytest.raises(ValueError,match='force'):
        proportion_test([[10,20],[30,40]],force)
