from types import SimpleNamespace

import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt
import numpy as np
import pandas as pd
import pytest

import PyFLASH.plotting as plotting
from PyFLASH.plotting import (
    _compute_correlation,
    _correlation_display_name,
    _correlation_pandas_method,
    _normalize_correlation_method,
    _render_value_matrix,
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


def test_render_value_matrix_lower_triangle_values_shift_stars():
    matrix = pd.DataFrame(
        [[1.0, 0.5], [0.5, 1.0]],
        index=["a", "b"],
        columns=["a", "b"],
    )
    annotations = pd.DataFrame("", index=matrix.index, columns=matrix.columns)
    annotations.loc["a", "b"] = "*"
    annotations.loc["b", "a"] = "*"

    fig, ax = plt.subplots()
    try:
        _render_value_matrix(
            matrix,
            ax=ax,
            fig=fig,
            annotations=annotations,
            triangle="lower",
            show_diagonal=False,
            show_values=True,
            value_format=".2f",
            show_colorbar=False,
        )

        texts = [(t.get_text(), t.get_position()) for t in ax.texts]
        assert [txt for txt, _ in texts] == ["0.50", "*"]
        value_y = texts[0][1][1]
        star_y = texts[1][1][1]
        assert star_y < value_y
    finally:
        plt.close(fig)


def test_matrix_action_lower_triangle_masks_hidden_cells():
    df = pd.DataFrame(
        {
            "a": [1, 2, 3, 4, 5],
            "b": [2, 4, 6, 8, 10],
            "c": [5, 4, 3, 2, 1],
        }
    )
    ctx = SimpleNamespace(factor_value=None, condition_df=df)
    fig, ax = plt.subplots()
    try:
        matrix_action(
            ctx,
            {"fig": fig, "ax": ax},
            filtered_columns=["a", "b", "c"],
            correlation="pearsonr",
            triangle="lower",
            show_diagonal=False,
            show_values=True,
        )

        heatmap_values = np.asarray(ax.collections[0].get_array())
        heatmap_mask = np.ma.getmaskarray(ax.collections[0].get_array()).reshape(3, 3)
        heatmap_matrix = heatmap_values.reshape(3, 3)

        assert heatmap_mask[0, 0]
        assert heatmap_mask[0, 1]
        assert heatmap_mask[1, 1]
        assert not heatmap_mask[1, 0]
        assert heatmap_matrix[1, 0] == pytest.approx(1.0)
    finally:
        plt.close(fig)


def test_rect_matrices_forwards_triangle_and_value_options(monkeypatch, tmp_path):
    calls = []

    def fake_render_value_matrix(matrix, **kwargs):
        calls.append(kwargs)
        return kwargs["fig"], kwargs["ax"], kwargs["ax"]

    monkeypatch.setattr(plotting, "_render_value_matrix", fake_render_value_matrix)
    exp = SimpleNamespace(
        summary=pd.DataFrame(
            {
                "Condition": ["A", "A", "A", "A"],
                "y1": [1.0, 2.0, 3.0, 4.0],
                "y2": [2.0, 4.0, 6.0, 8.0],
                "x1": [1.0, 2.0, 3.0, 4.0],
                "x2": [4.0, 3.0, 2.0, 1.0],
            }
        ),
        fig_path=str(tmp_path),
        condition_list=[SimpleNamespace(name="A", label="A", color="black")],
        aliases=None,
    )

    plotting.plot_rect_matrices(
        exp,
        filtered_columns=["y1", "y2"],
        against_columns=["x1", "x2"],
        save=False,
        triangle="lower",
        show_diagonal=False,
        show_values=True,
        value_format=".1f",
    )

    assert calls
    assert calls[0]["triangle"] == "lower"
    assert calls[0]["show_diagonal"] is False
    assert calls[0]["show_values"] is True
    assert calls[0]["value_format"] == ".1f"
    assert calls[0]["show_colorbar"] is False


def test_rect_matrices_handles_overlapping_axes_with_hidden_diagonal(tmp_path):
    exp = SimpleNamespace(
        summary=pd.DataFrame(
            {
                "Condition": ["A", "A", "A", "A", "A"],
                "a": [1.0, 2.0, 3.0, 4.0, 5.0],
                "b": [2.0, 4.0, 6.0, 8.0, 10.0],
                "c": [5.0, 4.0, 3.0, 2.0, 1.0],
            }
        ),
        fig_path=str(tmp_path),
        condition_list=[SimpleNamespace(name="A", label="A", color="black")],
        aliases=None,
    )

    out = plotting.plot_rect_matrices(
        exp,
        filtered_columns=["a", "b"],
        against_columns=["a", "b"],
        save=False,
        triangle="lower",
        show_diagonal=False,
        show_values=True,
    )

    assert out["A"]["correlations"]["a vs a"][1] == pytest.approx(1.0)
    assert out["A"]["correlations"]["b vs b"][1] == pytest.approx(1.0)
