import glob
import os
from types import SimpleNamespace

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd
import pytest

from PyFLASH import plotting, report
from PyFLASH.aesthetics import pyflash_style_context
from PyFLASH.spec import PLOT_REGISTRY, _resolve_func, describe_status


def _dataset(tmp_path):
    rng = np.random.default_rng(17)
    n = 40
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    z1 = rng.normal(size=n)
    z2 = rng.normal(size=n)
    signal = 2.0 * x1 - 1.25 * x2 + rng.normal(0, 0.08, size=n)
    noise = rng.normal(size=n)
    conds = (["WT"] * (n // 2)) + (["AD"] * (n - n // 2))
    summary = pd.DataFrame({
        "AnimalName": [f"S{i:02d}" for i in range(n)],
        "Condition": conds,
        "Diagnosis": conds,
        "x1": x1,
        "x2": x2,
        "z1": z1,
        "z2": z2,
        "Signal": signal,
        "Noise": noise,
    })
    fig_path = str(tmp_path / "Python Figures")
    os.makedirs(fig_path, exist_ok=True)
    return SimpleNamespace(
        summary=summary,
        summaries={"SCN": summary},
        fig_path=fig_path,
        condition_list=[
            SimpleNamespace(name="WT", label="WT", color="black"),
            SimpleNamespace(name="AD", label="AD", color="red"),
        ],
    )


def _svgs(fig_path):
    return glob.glob(os.path.join(fig_path, "**", "*.svg"), recursive=True)


def test_multivariable_regression_matrix_registered_and_covered():
    assert "multivariable_regression_matrix" in PLOT_REGISTRY
    assert _resolve_func(PLOT_REGISTRY["multivariable_regression_matrix"]).__name__ == (
        "plot_multivariable_regression_matrix"
    )
    assert describe_status("multivariable_regression_matrix") == "covered"


def test_multivariable_regression_matrix_detects_joint_signal_and_saves(tmp_path):
    exp = _dataset(tmp_path)
    out = plotting.plot_multivariable_regression_matrix(
        exp,
        filtered_columns=["Signal", "Noise"],
        predictors={"PairA": ["x1", "x2"], "PairB": ["z1", "z2"]},
        by="all",
    )

    signal_a = out["Combined"]["models"]["Signal ~ PairA"]
    noise_a = out["Combined"]["models"]["Noise ~ PairA"]
    assert signal_a["r2"] > 0.98
    assert signal_a["q"] < 0.001
    assert noise_a["r2"] < 0.3
    assert any("Multivariable Regression Matrix" in os.path.basename(f) for f in _svgs(exp.fig_path))


def test_multivariable_regression_matrix_emits_report_records(tmp_path):
    exp = _dataset(tmp_path)
    report.start()
    plotting.plot_multivariable_regression_matrix(
        exp,
        filtered_columns=["Signal"],
        predictors={"PairA": ["x1", "x2"]},
        by="all",
        save=False,
    )
    records = report.collect()

    assert len(records) == 1
    rec = records[0]
    assert rec["kind"] == "multivariable_regression"
    assert rec["predictor_set"] == "PairA"
    assert rec["predictors"] == ["x1", "x2"]
    assert rec["y"] == "Signal"
    assert rec["r2"] > 0.98


def test_multivariable_regression_matrix_default_columns_use_selected_roi_summary(tmp_path):
    exp = _dataset(tmp_path)
    ctx_summary = exp.summary.copy()
    ctx_summary["CTXOnly"] = (
        1.5 * ctx_summary["x1"] - 0.75 * ctx_summary["x2"]
    )
    exp.summaries = {
        "SCN": exp.summary,
        "CTX": ctx_summary,
    }

    out = plotting.plot_multivariable_regression_matrix(
        exp,
        predictors={"PairA": ["x1", "x2"]},
        by="all",
        roi="CTX",
        save=False,
    )

    assert "CTXOnly ~ PairA" in out["Combined"]["models"]
    assert out["Combined"]["models"]["CTXOnly ~ PairA"]["r2"] > 0.99


def test_multivariable_regression_matrix_uses_matrix_tick_style(tmp_path, monkeypatch):
    exp = _dataset(tmp_path)
    real_close = plotting.plt.close
    monkeypatch.setattr(plotting.plt, "close", lambda fig=None: None)

    with pyflash_style_context(matrix_x_tick_rotation=25, matrix_y_tick_rotation=10):
        plotting.plot_multivariable_regression_matrix(
            exp,
            filtered_columns=["Signal", "Noise"],
            predictors={"PairA": ["x1", "x2"], "PairB": ["z1", "z2"]},
            by="all",
            save=False,
        )

        fig = plotting.plt.gcf()
    try:
        ax = fig.axes[0]
        assert ax.get_xticklabels()[0].get_rotation() == pytest.approx(25)
        assert ax.get_yticklabels()[0].get_rotation() == pytest.approx(10)
        side_text = "\n".join(text.get_text() for text in ax.texts)
        assert "Test: multivariable OLS" in side_text
        assert "Signal ~ PairA" in side_text
        assert "p=" in side_text
        assert "q=" in side_text
    finally:
        real_close(fig)


def test_multivariable_regression_matrix_requires_valid_predictors(tmp_path):
    exp = _dataset(tmp_path)
    with pytest.raises(ValueError, match="predictor"):
        plotting.plot_multivariable_regression_matrix(
            exp,
            filtered_columns=["Signal"],
            predictors={"Broken": ["x1", "missing_column"]},
            by="all",
            save=False,
        )
