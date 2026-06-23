"""Tests for the correlation pipeline (matrix -> FDR/p gate -> regressions)."""
import os
from types import SimpleNamespace

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd
import pytest

from PyFLASH.batch import Batch
from PyFLASH.conditions import condition, conditionList
from PyFLASH.experiment import MiniExperiment
from PyFLASH.plotting import (
    _corr_pipeline_compute,
    _corr_pipeline_run_dirs,
    _corr_pipeline_slug,
    plot_correlation_pipeline,
    plot_matrix_differences,
)


# ── Helpers ──────────────────────────────────────────────────────────────

def _pairs_of(frame):
    if len(frame) == 0:
        return set()
    return set(zip(frame["x"], frame["y"]))


def _expected_selected(long_df, gate, require, alpha):
    """Re-derive the surviving pairs straight from the reported p/q values."""
    use_q = gate in ("fdr", "q")
    col = "q" if use_q else "p"
    out = set()
    for (x, y), grp in long_df.groupby(["x", "y"]):
        sig = grp[col] < alpha  # NaN < alpha -> False
        passed = sig.all() if require == "and" else sig.any()
        if passed:
            out.add((x, y))
    return out


def _logic_frame():
    """Numeric frame with a spread of correlation strengths (fixed seed)."""
    rng = np.random.default_rng(0)
    n = 30
    base = np.arange(n, dtype=float)
    return pd.DataFrame({
        "a": base,
        "b": 2.0 * base + rng.normal(0, 0.5, n),      # strong positive
        "c": -base + rng.normal(0, 0.5, n),           # strong negative
        "d": rng.normal(0, 1, n),                     # independent
        "e": base + rng.normal(0, 6.0, n),            # moderate / borderline
        "f": rng.normal(0, 1, n),                     # independent
    })


# ── Gating logic: AND/OR x p/FDR ─────────────────────────────────────────

@pytest.mark.parametrize("gate", ["p", "fdr"])
@pytest.mark.parametrize("require", ["and", "or"])
def test_selection_matches_reported_stats(gate, require):
    df = _logic_frame()
    cols = list(df.columns)
    res = _corr_pipeline_compute(
        df, cols, cols, ["pearsonr", "spearmanr", "kendalltau"],
        gate=gate, alpha=0.05, require=require, min_n=3, square=True,
    )
    expected = _expected_selected(res["long"], gate, require, 0.05)
    assert _pairs_of(res["selected"]) == expected


def test_and_is_subset_of_or_and_fdr_subset_of_p():
    df = _logic_frame()
    cols = list(df.columns)

    def sel(gate, require):
        res = _corr_pipeline_compute(
            df, cols, cols, ["pearsonr", "spearmanr", "kendalltau"],
            gate=gate, alpha=0.05, require=require, min_n=3, square=True,
        )
        return _pairs_of(res["selected"])

    # AND can never select a pair that OR would not.
    assert sel("p", "and") <= sel("p", "or")
    assert sel("fdr", "and") <= sel("fdr", "or")
    # FDR q-values are >= raw p-values, so the FDR gate is at least as strict.
    assert sel("fdr", "or") <= sel("p", "or")
    # The strong, perfectly/near-perfectly correlated pairs survive every gate.
    assert ("a", "b") in sel("fdr", "and")
    assert ("a", "c") in sel("fdr", "and")
    # Independent columns never survive.
    assert ("d", "f") not in sel("p", "or")


def test_matrix_is_symmetric_with_unit_diagonal():
    df = _logic_frame()
    cols = list(df.columns)
    res = _corr_pipeline_compute(
        df, cols, cols, ["pearsonr"], gate="p", alpha=0.05,
        require="and", min_n=3, square=True,
    )
    coef = res["coef"]["pearsonr"]
    assert list(coef.index) == cols and list(coef.columns) == cols
    np.testing.assert_allclose(np.diag(coef.to_numpy()), 1.0)
    np.testing.assert_allclose(coef.to_numpy(), coef.to_numpy().T, equal_nan=True)


def test_min_n_blocks_underpowered_pairs():
    df = pd.DataFrame({
        "a": [1.0, 2, 3, 4, 5, 6],
        "b": [2.0, 4, 6, 8, 10, 12],
        "sparse": [1.0, np.nan, np.nan, np.nan, 2.0, np.nan],  # only 2 overlap
    })
    cols = ["a", "b", "sparse"]
    res = _corr_pipeline_compute(
        df, cols, cols, ["pearsonr"], gate="p", alpha=0.05,
        require="and", min_n=3, square=True,
    )
    sp = res["long"][(res["long"].x == "a") & (res["long"].y == "sparse")].iloc[0]
    assert sp["n"] == 2
    assert pd.isna(sp["r"])
    selected = _pairs_of(res["selected"])
    assert ("a", "sparse") not in selected
    assert ("a", "b") in selected  # perfect line still passes


def test_rectangular_mode_shapes():
    df = _logic_frame()
    res = _corr_pipeline_compute(
        df, ["a", "b"], ["d", "e", "f"], ["pearsonr"],
        gate="p", alpha=0.05, require="or", min_n=3, square=False,
    )
    coef = res["coef"]["pearsonr"]
    assert list(coef.index) == ["a", "b"]
    assert list(coef.columns) == ["d", "e", "f"]


# ── Run naming + collision policy ────────────────────────────────────────

def test_slug_is_deterministic_and_config_sensitive():
    args = (["a", "b", "c"], [], ["pearsonr", "spearmanr"], "and", "fdr",
            0.05, "all", None, None, None)
    s1 = _corr_pipeline_slug(*args)
    s2 = _corr_pipeline_slug(*args)
    assert s1 == s2
    assert s1.startswith("3cols_PS_fdr_")
    # Different columns -> different folder.
    s_cols = _corr_pipeline_slug(["a", "b", "d"], [], ["pearsonr", "spearmanr"],
                                 "and", "fdr", 0.05, "all", None, None, None)
    assert s_cols != s1
    # Different gate -> different folder.
    s_gate = _corr_pipeline_slug(["a", "b", "c"], [], ["pearsonr", "spearmanr"],
                                 "and", "p", 0.05, "all", None, None, None)
    assert s_gate != s1


def test_if_exists_policies(tmp_path):
    exp = SimpleNamespace(fig_path=str(tmp_path / "fig"),
                          data_path=str(tmp_path / "data"))

    # No existing folder -> use the name as-is.
    fig_dir, _data_dir, label, reuse = _corr_pipeline_run_dirs(exp, "run", "overwrite")
    assert label == "run" and reuse is False

    os.makedirs(fig_dir)  # simulate a previous run on disk

    # overwrite reuses the same folder in place.
    _f, _d, label_ow, reuse_ow = _corr_pipeline_run_dirs(exp, "run", "overwrite")
    assert label_ow == "run" and reuse_ow is False

    # version picks the next free suffix, preserving the prior run.
    _f, _d, label_v, _ = _corr_pipeline_run_dirs(exp, "run", "version")
    assert label_v == "run_v2"

    # skip flags the caller to reuse the cached manifest.
    _f, _d, _l, reuse_skip = _corr_pipeline_run_dirs(exp, "run", "skip")
    assert reuse_skip is True

    # error refuses to touch an existing run.
    with pytest.raises(RuntimeError):
        _corr_pipeline_run_dirs(exp, "run", "error")

    # an unknown policy is rejected.
    with pytest.raises(ValueError):
        _corr_pipeline_run_dirs(exp, "run", "bogus")


# ── End-to-end against a real Batch ──────────────────────────────────────

def _human_batch(tmp_path):
    a = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
    b = [2.1, 3.9, 6.2, 8.1, 9.8, 12.2, 13.9, 16.1, 18.2, 19.8, 22.1, 24.0]
    c = [12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1]
    d = [3, 1, 4, 1, 5, 9, 2, 6, 5, 3, 5, 8]
    diag = ["AD", "MCI", "Control"] * 4
    lines = ["ID,Diagnosis,Ma,Mb,Mc,Md"]
    for i in range(12):
        lines.append(f"{i + 1},{diag[i]},{a[i]},{b[i]},{c[i]},{d[i]}")
    os.makedirs(tmp_path, exist_ok=True)
    with open(os.path.join(tmp_path, "Data.csv"), "w", encoding="utf-8", newline="") as fh:
        fh.write("\n".join(lines))

    exp = MiniExperiment(
        "Human", str(tmp_path), animal_column="ID",
        factor_mappings={"Diagnosis": {"AD": "AD", "MCI": "MCI", "Control": "Control"}},
    )
    diagnosis = conditionList([
        condition("AD", "AD", "#9f1c1f", "Diagnosis"),
        condition("MCI", "MCI", "#4369b2", "Diagnosis"),
        condition("Control", "Control", "#787a7c", "Diagnosis"),
    ])
    batch = Batch("human", [exp], diagnosis, str(tmp_path))
    batch.processData(import_images=False, progress=False)
    return batch


def test_pipeline_end_to_end_outputs(tmp_path):
    batch = _human_batch(tmp_path)
    cols = [c for c in ["Ma", "Mb", "Mc", "Md"] if c in batch.summary.columns]
    assert len(cols) == 4, f"expected metric columns, got {list(batch.summary.columns)}"

    res = plot_correlation_pipeline(
        batch, filtered_columns=cols, by="all",
        tests=("pearsonr", "spearmanr", "kendalltau"),
        require="and", gate="fdr", alpha=0.05,
        regression_factor="Diagnosis", max_regressions=3,
        run_label="e2e", save=True,
    )

    assert res["run_label"] == "e2e"
    data_dir = res["data_dir"]
    fig_dir = res["fig_dir"]

    # Tables.
    for name in ("pairwise_correlations.csv", "selected_pairs.csv", "manifest.json"):
        assert os.path.isfile(os.path.join(data_dir, name)), name
    for disp in ("Pearson", "Spearman", "Kendall"):
        assert os.path.isfile(os.path.join(data_dir, f"coef_{disp}.csv"))
        assert os.path.isfile(os.path.join(data_dir, f"pvalues_{disp}.csv"))
        assert os.path.isfile(os.path.join(data_dir, f"qvalues_{disp}.csv"))
    assert os.path.isfile(os.path.join(os.path.dirname(data_dir), "_runs_index.csv"))

    # Matrix figures: coefficient, raw p-value, FDR q-value, and gate overview.
    matrices = os.path.join(fig_dir, "Matrices")
    svgs = [f for f in os.listdir(matrices) if f.endswith(".svg")]
    assert any("Pearson" in f for f in svgs)
    assert any("Pearson PValue Matrix" in f for f in svgs)
    assert any("Pearson FDR QValue Matrix" in f for f in svgs)
    assert any("Gate" in f for f in svgs)

    # The strongly correlated metric trio survives the strict gate and is plotted.
    assert res["n_selected"] >= 3
    assert res["n_regressions"] >= 1
    reg_svgs = []
    for root, _dirs, files in os.walk(os.path.join(fig_dir, "Regressions")):
        reg_svgs += [f for f in files if f.endswith(".svg")]
    assert reg_svgs, "expected at least one regression figure"

    # fig_path must be restored after the regression redirect.
    assert batch.fig_path.endswith("Python Figures")
    assert "Correlation Pipeline" not in batch.fig_path


def test_pipeline_can_skip_plotted_pq_matrices(tmp_path):
    batch = _human_batch(tmp_path)
    cols = [c for c in ["Ma", "Mb", "Mc", "Md"] if c in batch.summary.columns]

    res = plot_correlation_pipeline(
        batch, filtered_columns=cols, by="all",
        tests=("pearsonr", "spearmanr"), require="and", gate="fdr",
        max_regressions=0, run_label="no_pq_heatmaps", save=True,
        plot_pvalue_matrices=False, plot_qvalue_matrices=False,
    )

    matrices = os.path.join(res["fig_dir"], "Matrices")
    svgs = [f for f in os.listdir(matrices) if f.endswith(".svg")]
    assert any("Pearson Correlation Matrix" in f for f in svgs)
    assert any("Gate Passing Matrix" in f for f in svgs)
    assert not any("PValue Matrix" in f for f in svgs)
    assert not any("QValue Matrix" in f for f in svgs)

    # The tables are still part of the run even when the heatmaps are skipped.
    assert os.path.isfile(os.path.join(res["data_dir"], "pvalues_Pearson.csv"))
    assert os.path.isfile(os.path.join(res["data_dir"], "qvalues_Pearson.csv"))


def test_plot_matrix_differences_outputs_and_values(tmp_path):
    batch = _human_batch(tmp_path)
    cols = [c for c in ["Ma", "Mb", "Mc", "Md"] if c in batch.summary.columns]

    res = plot_matrix_differences(
        batch,
        filtered_columns=cols,
        factor="Diagnosis",
        comparisons=["1-2"],
        correlation=("pearsonr", "spearmanr"),
        min_n=3,
        run_label="diag_diff",
        save=True,
    )

    assert res["run_label"] == "diag_diff"
    assert res["comparisons"][0]["left_group"] == "AD"
    assert res["comparisons"][0]["right_group"] == "MCI"
    assert os.path.isfile(os.path.join(res["data_dir"], "manifest.json"))

    comp_dirs = [
        root for root, _dirs, files in os.walk(res["data_dir"])
        if "signed_delta_Pearson.csv" in files
    ]
    assert comp_dirs, "expected per-comparison difference CSVs"
    signed = pd.read_csv(os.path.join(comp_dirs[0], "signed_delta_Pearson.csv"), index_col=0)

    summary = batch.summary
    ad = summary[summary["Diagnosis"] == "AD"][["Ma", "Mb"]].corr(method="pearson").loc["Ma", "Mb"]
    mci = summary[summary["Diagnosis"] == "MCI"][["Ma", "Mb"]].corr(method="pearson").loc["Ma", "Mb"]
    assert signed.loc["Ma", "Mb"] == pytest.approx(ad - mci)

    diff_rows = res["differences"]
    row = diff_rows[
        (diff_rows["comparison"] == "AD vs MCI")
        & (diff_rows["method"] == "Pearson")
        & (diff_rows["x"] == "Ma")
        & (diff_rows["y"] == "Mb")
    ].iloc[0]
    assert row["absolute_delta"] == pytest.approx(abs(ad - mci))
    assert row["difference_test"] == "Fisher z"

    matrix_svgs = []
    for root, _dirs, files in os.walk(res["fig_dir"]):
        matrix_svgs.extend(files)
    assert any("Pearson Signed Difference Matrix" in f for f in matrix_svgs)
    assert any("Pearson Absolute Difference Matrix" in f for f in matrix_svgs)
    assert any("Pearson Difference PValue Matrix" in f for f in matrix_svgs)
    assert not any("Spearman Difference PValue Matrix" in f for f in matrix_svgs)


def test_pipeline_writes_difference_matrices(tmp_path):
    batch = _human_batch(tmp_path)
    cols = [c for c in ["Ma", "Mb", "Mc", "Md"] if c in batch.summary.columns]

    res = plot_correlation_pipeline(
        batch,
        filtered_columns=cols,
        factor="Diagnosis",
        tests=("pearsonr", "spearmanr"),
        require="and",
        gate="fdr",
        max_regressions=0,
        run_label="pipeline_diff",
        plot_difference_matrices=True,
        difference_comparisons=["1-2"],
        save=True,
    )

    diff = res["difference_matrices"]
    assert diff["enabled"] is True
    assert diff["n_comparisons"] == 1
    assert diff["comparisons"][0]["left_group"] == "AD"
    assert diff["comparisons"][0]["right_group"] == "MCI"

    diff_data = os.path.join(res["data_dir"], "Matrix Differences")
    diff_fig = os.path.join(res["fig_dir"], "Matrix Differences")
    assert os.path.isfile(os.path.join(diff_data, "matrix_differences.csv"))
    assert any(
        f.endswith(".svg") and "Signed Difference Matrix" in f
        for _root, _dirs, files in os.walk(diff_fig)
        for f in files
    )


def test_pipeline_auto_naming_and_versioning(tmp_path):
    batch = _human_batch(tmp_path)
    cols = [c for c in ["Ma", "Mb", "Mc", "Md"] if c in batch.summary.columns]

    auto = plot_correlation_pipeline(
        batch, filtered_columns=cols, tests=("pearsonr", "spearmanr", "kendalltau"),
        gate="fdr", require="and", max_regressions=0, save=True,
    )
    assert auto["run_label"].startswith("4cols_PSK_fdr_")

    # Same settings -> same auto folder (idempotent overwrite).
    again = plot_correlation_pipeline(
        batch, filtered_columns=cols, tests=("pearsonr", "spearmanr", "kendalltau"),
        gate="fdr", require="and", max_regressions=0, save=True,
    )
    assert again["run_label"] == auto["run_label"]

    # A different column set -> a different folder.
    fewer = plot_correlation_pipeline(
        batch, filtered_columns=cols[:3], tests=("pearsonr", "spearmanr", "kendalltau"),
        gate="fdr", require="and", max_regressions=0, save=True,
    )
    assert fewer["run_label"] != auto["run_label"]

    # Explicit label + version policy preserves the earlier run.
    first = plot_correlation_pipeline(
        batch, filtered_columns=cols, run_label="keep", if_exists="version",
        max_regressions=0, save=True,
    )
    second = plot_correlation_pipeline(
        batch, filtered_columns=cols, run_label="keep", if_exists="version",
        max_regressions=0, save=True,
    )
    assert first["run_label"] == "keep"
    assert second["run_label"] == "keep_v2"
