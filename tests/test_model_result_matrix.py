import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt
import pandas as pd
import pytest

from PyFLASH import plotting, report, from_dataframe
from PyFLASH.batch import Batch
from PyFLASH.conditions import condition, conditionList
from PyFLASH.experiment import Experiment
from PyFLASH.spec import PLOT_REGISTRY, _resolve_func, describe_status


def _model_frame():
    rows = []
    values = {
        ("amplitude", "Control", "Month"): (0.80, 0.010, 0.030),
        ("amplitude", "Control", "Season"): (0.42, 0.300, 0.500),
        ("amplitude", "AD", "Month"): (0.20, 0.500, 0.700),
        ("amplitude", "AD", "Season"): (0.10, 0.800, 0.900),
        ("period", "Control", "Month"): (0.12, 0.600, 0.700),
        ("period", "Control", "Season"): (0.31, 0.200, 0.350),
        ("period", "AD", "Month"): (0.22, 0.070, 0.180),
        ("period", "AD", "Season"): (0.45, 0.040, 0.120),
    }
    labels = {"amplitude": "Amplitude", "period": "Period"}
    for (outcome, diagnosis, predictor), (r2, p, q) in values.items():
        rows.append(
            {
                "outcome": outcome,
                "label": labels[outcome],
                "Diagnosis": diagnosis,
                "predictor": predictor,
                "r2": r2,
                "p": p,
                "q": q,
            }
        )
    return pd.DataFrame(rows)


def test_model_result_matrix_registered_and_covered():
    assert PLOT_REGISTRY["model_result_matrix"] == "plot_model_result_matrix"
    assert _resolve_func(PLOT_REGISTRY["model_result_matrix"]).__name__ == (
        "plot_model_result_matrix"
    )
    assert describe_status("model_result_matrix") == "covered"


def test_model_result_matrix_accepts_csv_path_and_saves_editable_svg(tmp_path):
    csv_path = tmp_path / "model_results.csv"
    _model_frame().to_csv(csv_path, index=False)

    out = plotting.plot_model_result_matrix(
        path=csv_path,
        row_col="outcome",
        row_label_col="label",
        group_col="Diagnosis",
        profile_col="predictor",
        value_col="r2",
        row_order=["period", "amplitude"],
        group_order=["Control", "AD"],
        profile_order=["Month", "Season"],
        title="Month and season models",
        filename="model_matrix",
        save=True,
    )

    output = Path(out["path"])
    assert output.exists()
    assert output.parent.name == "Model Results"
    svg = output.read_text(encoding="utf-8")
    assert "<text" in svg
    assert "0.80*+" in svg
    assert "0.45*" in svg
    assert "Control" in svg and "Month" in svg
    assert "Model in each cell: y ~ Month/Season within Diagnosis." in svg
    assert list(out["values"].index) == ["Period", "Amplitude"]
    assert out["vmin"] == 0.0
    assert out["vmax"] == 0.8


def test_model_result_matrix_accepts_experiment_object_summary(tmp_path):
    exp = Experiment("model", str(tmp_path))
    exp.summary = _model_frame()
    exp.fig_path = str(tmp_path / "figures")
    exp.aliases = {}
    os.makedirs(exp.fig_path, exist_ok=True)

    out = plotting.plot_model_result_matrix(exp, save=False)
    try:
        assert out["values"].shape == (2, 4)
        assert out["annotations"].loc["Amplitude", "Control\nMonth"] == "0.80*+"
    finally:
        plt.close(out["figure"])


def test_model_result_matrix_grouped_headers_and_palette(tmp_path):
    out = plotting.plot_model_result_matrix(
        _model_frame(),
        group_order=["Control", "AD"],
        profile_order=["Month", "Season"],
        palette="Greens",
        save=False,
    )
    try:
        fig = out["figure"]
        ax = fig.axes[0]
        assert ax.collections[0].cmap.name.lower().startswith("greens")
        assert fig.axes[1].get_position().width == pytest.approx(0.024)
        assert [label.get_text() for label in ax.get_xticklabels()] == [
            "Month",
            "Season",
            "Month",
            "Season",
        ]
        header_texts = [
            text.get_text()
            for text in ax.texts
            if text.get_text() in {"Control", "AD"}
        ]
        assert header_texts == ["Control", "AD"]
        assert any("y ~ Month/Season" in text.get_text() for text in ax.texts)
        side_text = "\n".join(text.get_text() for text in ax.texts)
        assert "Results: precomputed model table" in side_text
        assert "Amplitude ~ Month [Control]: R2=0.8, p=0.01, q=0.03" in side_text
        assert out["vmax"] == 0.8
    finally:
        plt.close(out["figure"])


def test_model_result_matrix_accepts_batch_roi_summary(tmp_path):
    conds = conditionList(
        [
            condition("Control", "Control", "black", "Diagnosis"),
            condition("AD", "AD", "red", "Diagnosis"),
        ]
    )
    batch = Batch("model", [], conds, str(tmp_path))
    batch.createSavePaths()
    os.makedirs(batch.fig_path, exist_ok=True)
    scn = _model_frame()
    ctx = _model_frame()
    ctx["r2"] = ctx["r2"] / 2.0
    batch.summary = scn
    batch.summaries = {"SCN": scn, "CTX": ctx}
    batch.aliases = {}

    out = plotting.plot_model_result_matrix(batch, roi="CTX", save=False)
    try:
        assert out["source_name"] == "CTX"
        assert out["values"].loc["Amplitude", "Control\nMonth"] == 0.40
    finally:
        plt.close(out["figure"])


def test_model_result_matrix_accepts_dataframe_experiment_named_table(tmp_path):
    exp = from_dataframe(
        pd.DataFrame({"AnimalName": ["S1"], "Condition": ["Control"]}),
        group_col="Condition",
        subject_col="AnimalName",
        fig_path=tmp_path / "figures",
    )
    exp.model_results = _model_frame()

    out = plotting.plot_model_result_matrix(exp, model_table="model_results", save=False)
    try:
        assert out["source_name"] == "model_results"
        assert out["group_col"] == "Diagnosis"
        assert "AD\nSeason" in out["values"].columns
    finally:
        plt.close(out["figure"])


def test_model_result_matrix_emits_report_records():
    report.start()
    out = plotting.plot_model_result_matrix(_model_frame(), save=False)
    try:
        records = report.collect()
    finally:
        plt.close(out["figure"])

    assert len(records) == 8
    assert {rec["kind"] for rec in records} == {"model_result_matrix"}
    first = records[0]
    assert first["metric"] == "Amplitude"
    assert first["group"] == "Control"
    assert first["profile"] == "Month"
    assert first["value"] == 0.80
    assert first["p"] == 0.010
    assert first["q"] == 0.030
    assert first["significance"] == ["raw_p", "fdr_q"]
