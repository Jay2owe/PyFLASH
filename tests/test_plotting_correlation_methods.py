from types import SimpleNamespace

import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt
import numpy as np
import pandas as pd
import pytest

from PyFLASH.plotting import (
    _compute_correlation,
    _correlation_display_name,
    _correlation_pandas_method,
    _normalize_correlation_method,
    matrix_action,
)


def test_correlation_method_aliases_include_kendall():
    assert _normalize_correlation_method("p") == "pearsonr"
    assert _normalize_correlation_method("pearson") == "pearsonr"
    assert _normalize_correlation_method("s") == "spearmanr"
    assert _normalize_correlation_method("spearman") == "spearmanr"
    assert _normalize_correlation_method("k") == "kendalltau"
    assert _normalize_correlation_method("kendall") == "kendalltau"
    assert _normalize_correlation_method("kendall_tau") == "kendalltau"
    assert _correlation_pandas_method("p") == "pearson"
    assert _correlation_pandas_method("s") == "spearman"
    assert _correlation_pandas_method("kendall") == "kendall"
    assert _correlation_display_name("k") == "Kendall"


def test_kendall_correlation_computes_expected_coefficient():
    x = pd.Series([1, 2, 3, 4])
    y = pd.Series([4, 1, 3, 2])

    coefficient, p_value = _compute_correlation(x, y, "kendall")

    assert coefficient == pytest.approx(-1 / 3)
    assert 0 <= p_value <= 1


def test_matrix_action_uses_selected_method_for_heatmap_and_pvalues():
    df = pd.DataFrame(
        {
            "a": [1, 2, 3, 4],
            "b": [4, 1, 3, 2],
        }
    )
    ctx = SimpleNamespace(factor_value=None, condition_df=df)
    fig, ax = plt.subplots()
    try:
        result = matrix_action(
            ctx,
            {"fig": fig, "ax": ax},
            filtered_columns=["a", "b"],
            correlation="kendall",
        )

        coefficient = result["correlations"]["a vs b"][1]
        heatmap_values = np.asarray(ax.collections[0].get_array())
        if np.ma.isMaskedArray(heatmap_values):
            heatmap_values = heatmap_values.filled(np.nan)
        heatmap_matrix = heatmap_values.reshape(2, 2)

        assert coefficient == pytest.approx(-1 / 3)
        assert heatmap_matrix[0, 1] == pytest.approx(-1 / 3)
        assert heatmap_matrix[1, 0] == pytest.approx(-1 / 3)
    finally:
        plt.close(fig)
