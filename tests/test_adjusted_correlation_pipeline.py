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


def test_adjusted_correlation_default_value_matrix_heatmap_is_p_value(tmp_path):
    exp = _adjusted_dataset(tmp_path)

    res = pipeline.adjusted_correlation(
        exp,
        endpoints=["A", "B", "C"],
        tests=("pearsonr",),
        max_adjusted_regressions=0,
        run_label="adjusted_default_p_matrix",
        save=True,
        verbose=False,
    )

    assert res["gate"] == "p"
    assert res["value_matrices"] == "p"
    assert res["plot_pvalue_matrices"] is True
    assert res["plot_qvalue_matrices"] is False
    assert res["coefficient_matrix_star_source"] == "raw_p_value"
    assert res["data_dir"] == res["fig_dir"]

    matrices = os.path.join(res["fig_dir"], "Matrices")
    svgs = [f for f in os.listdir(matrices) if f.endswith(".svg")]
    for block in ("Raw", "Adjusted"):
        assert any(f"Pearson PValue Matrix_{block}" in f for f in svgs)
        assert not any(f"Pearson FDR QValue Matrix_{block}" in f for f in svgs)
        coef_svg = next(f for f in svgs if f"Pearson Correlation Matrix_{block}" in f)
        with open(os.path.join(matrices, coef_svg), encoding="utf-8") as handle:
            coef_text = handle.read()
        assert "(* p&lt;0.05)" in coef_text or "(* p<0.05)" in coef_text
        assert "(* q&lt;0.05)" not in coef_text and "(* q<0.05)" not in coef_text
        assert os.path.isfile(os.path.join(matrices, f"pvalues_Pearson_{block}.csv"))
        assert os.path.isfile(os.path.join(matrices, f"qvalues_Pearson_{block}.csv"))
        assert not os.path.exists(os.path.join(res["data_dir"], f"pvalues_Pearson_{block}.csv"))
        assert not os.path.exists(os.path.join(res["data_dir"], f"qvalues_Pearson_{block}.csv"))


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
    assert data_dir == res["fig_dir"]
    assert os.path.isfile(os.path.join(data_dir, "manifest.json"))
    assert os.path.isfile(os.path.join(data_dir, "covariate_screening.csv"))
    assert os.path.isfile(os.path.join(data_dir, "adjusted_regression_coefficients.csv"))
    # Raw/Adjusted blocks are flattened into one folder, distinguished by a tag.
    assert os.path.isfile(os.path.join(data_dir, "pairwise_correlations_Raw.csv"))
    assert os.path.isfile(os.path.join(data_dir, "pairwise_correlations_Adjusted.csv"))


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


def test_adjusted_correlation_specificity_queue_merges_into_one_folder(tmp_path):
    # A specificity queue writes every condition into ONE shared run folder, each
    # condition's Raw/Adjusted matrices + tables distinguished by a concise tag.
    exp = _adjusted_dataset(tmp_path)
    exp.summary["Diagnosis"] = ["Control"] * 18 + ["AD"] * 18

    res = pipeline.adjusted_correlation(
        exp,
        endpoints=["A", "B", "C"],
        covariates=["Sex"],
        categorical=["Sex"],
        reference_levels={"Sex": "F"},
        specificity=[("Diagnosis", "Control"), ("Diagnosis", "AD")],
        tests=("pearsonr",),
        require="or",
        gate="p",
        min_n=6,
        max_adjusted_regressions=0,
        run_label="adjusted_diag_queue",
        save=True,
    )

    assert res.get("queued") is not True
    assert res["pipeline"] == "adjusted_correlation"
    assert os.path.basename(res["data_dir"]) == "adjusted_diag_queue"
    assert os.path.isfile(os.path.join(res["data_dir"], "manifest.json"))
    assert {tuple(c["specificity"]) for c in res["conditions"]} == {
        ("Diagnosis", "Control"), ("Diagnosis", "AD")}

    # Both conditions' Adjusted-block tables sit flat in one data folder.
    data_files = set(os.listdir(res["data_dir"]))
    assert "pairwise_correlations_Adjusted_Diagnosis.Control.csv" in data_files
    assert "pairwise_correlations_Adjusted_Diagnosis.AD.csv" in data_files
    # Per-condition covariate screening is tagged too (no overwrite).
    assert "covariate_screening_Diagnosis.Control.csv" in data_files
    assert "covariate_screening_Diagnosis.AD.csv" in data_files

    # Both conditions' coefficient matrices live side-by-side in one Matrices/.
    svgs = set(os.listdir(os.path.join(res["fig_dir"], "Matrices")))
    assert "Pearson Correlation Matrix_Adjusted_Diagnosis.Control.svg" in svgs
    assert "Pearson Correlation Matrix_Adjusted_Diagnosis.AD.svg" in svgs
    # One combined overview montage spans the whole queue.
    assert res.get("montage") and os.path.isfile(res["montage"])

    # Combined manifest reports queue-level totals (nested raw/adjusted summed),
    # not first-condition values, and records per-condition covariate outcomes.
    assert res["n_conditions"] == 2
    assert res["adjusted"]["n_selected"] == sum(
        c["adjusted_n_selected"] for c in res["conditions"])
    for c in res["conditions"]:
        assert c["n_final_covariates"] is not None
    # First-condition-only per-group detail is not carried on the merged manifest.
    assert "groups" not in res["adjusted"]


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
