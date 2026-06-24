"""Tests for adjusted correlation pipeline covariate screening/residualization."""

from types import SimpleNamespace
import os

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd
import pytest
from scipy import stats as sp_stats

from PyFLASH import pipeline


def _adjusted_dataset(tmp_path):
    rng = np.random.default_rng(42)
    n = 36
    age = np.linspace(50, 85, n)
    a = 0.8 * age + rng.normal(0, 1.2, n)
    b = -0.7 * age + rng.normal(0, 1.2, n)
    c = np.sin(np.arange(n) * 2.1)
    sex = np.where(np.arange(n) % 2 == 0, "F", "M")
    summary = pd.DataFrame({
        "AnimalName": [f"S{i:02d}" for i in range(n)],
        "A": a,
        "B": b,
        "C": c,
        "Age": age,
        "Sex": sex,
    })
    fig_path = str(tmp_path / "Python Figures")
    data_path = str(tmp_path / "Data and Stats")
    os.makedirs(fig_path, exist_ok=True)
    os.makedirs(data_path, exist_ok=True)
    return SimpleNamespace(
        summary=summary,
        fig_path=fig_path,
        data_path=data_path,
        condition_list=[],
    )


def _pair_r(frame, x, y):
    row = frame[
        (frame["method"] == "Pearson")
        & (((frame["x"] == x) & (frame["y"] == y))
           | ((frame["x"] == y) & (frame["y"] == x)))
    ].iloc[0]
    return float(row["r"])


def _pair_row(frame, x, y):
    return frame[
        (frame["method"] == "Pearson")
        & (((frame["x"] == x) & (frame["y"] == y))
           | ((frame["x"] == y) & (frame["y"] == x)))
    ].iloc[0]


def _ordinary_pearson_p_from_r(r, n):
    if abs(float(r)) >= 1:
        return 0.0
    t_stat = float(r) * np.sqrt((int(n) - 2) / max(1 - float(r) ** 2, np.finfo(float).eps))
    return float(2 * sp_stats.t.sf(abs(t_stat), int(n) - 2))


def test_adjusted_correlation_promotes_candidate_removes_endpoint_and_saves(tmp_path):
    exp = _adjusted_dataset(tmp_path)

    res = pipeline.adjusted_correlation(
        exp,
        endpoints=["A", "B", "C", "Age"],
        covariates=["Sex"],
        candidate_covariates=["Age"],
        reference_levels={"Sex": "F"},
        tests=("pearsonr",),
        gate="p",
        covariate_gate="fdr",
        covariate_alpha=0.05,
        min_endpoint_hits=1,
        max_adjusted_regressions=4,
        plot_pvalue_matrices=False,
        plot_qvalue_matrices=False,
        run_label="adjusted_age",
        save=True,
    )

    assert res["promoted_covariates"] == ["Age"]
    assert res["final_covariates"] == ["Sex", "Age"]
    assert "Age" not in res["final_endpoints"]
    assert set(res["final_endpoints"]) == {"A", "B", "C"}
    assert res["covariate_screening"]["promoted"].any()

    raw_r = abs(_pair_r(res["raw"]["pairwise"], "A", "B"))
    adjusted_row = _pair_row(res["adjusted"]["pairwise"], "A", "B")
    adjusted_r = abs(float(adjusted_row["r"]))
    assert adjusted_r < raw_r * 0.5
    ordinary_residual_p = _ordinary_pearson_p_from_r(
        adjusted_row["r"], adjusted_row["n"])
    assert adjusted_row["adjusted_df_resid"] < adjusted_row["n"] - 2
    assert adjusted_row["p"] > ordinary_residual_p

    coeffs = res["adjusted_regression_coefficients"]
    assert not coeffs.empty
    assert coeffs["is_primary_predictor"].any()

    data_dir = res["data_dir"]
    assert os.path.isfile(os.path.join(data_dir, "manifest.json"))
    assert os.path.isfile(os.path.join(data_dir, "covariate_screening.csv"))
    assert os.path.isfile(os.path.join(data_dir, "adjusted_regression_coefficients.csv"))
    assert os.path.isfile(os.path.join(data_dir, "Raw", "pairwise_correlations.csv"))
    assert os.path.isfile(os.path.join(data_dir, "Adjusted", "pairwise_correlations.csv"))


def test_candidate_that_is_not_promoted_stays_endpoint(tmp_path):
    exp = _adjusted_dataset(tmp_path)

    res = pipeline.adjusted_correlation(
        exp,
        endpoints=["A", "B", "C"],
        covariates=["Sex"],
        candidate_covariates=["C"],
        reference_levels={"Sex": "F"},
        tests=("pearsonr",),
        gate="p",
        covariate_gate="fdr",
        covariate_alpha=1e-12,
        min_endpoint_hits=1,
        max_adjusted_regressions=0,
        run_label="unpromoted",
        save=False,
    )

    assert res["promoted_covariates"] == []
    assert "C" in res["final_endpoints"]
    assert res["final_covariates"] == ["Sex"]


def test_always_covariate_cannot_also_be_endpoint(tmp_path):
    exp = _adjusted_dataset(tmp_path)

    with pytest.raises(ValueError, match="candidate_covariates"):
        pipeline.adjusted_correlation(
            exp,
            endpoints=["A", "B", "Age"],
            covariates=["Age"],
            candidate_covariates=[],
            tests=("pearsonr",),
            save=False,
        )
