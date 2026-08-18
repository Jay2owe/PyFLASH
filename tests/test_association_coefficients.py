"""Focused coverage for the multi-association coefficient plot."""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from matplotlib.figure import Figure

from PyFLASH import report
from PyFLASH.batch import Batch
from PyFLASH.conditions import ConditionBuilder
from PyFLASH.dataframe import DataFrameExperiment, from_dataframe
from PyFLASH.experiment import MiniExperiment
from PyFLASH.plotting import plot_association_coefficients
from PyFLASH.spec import PLOT_REGISTRY, describe_status


GROUP_ORDER = ["Control", "MCI", "AD"]
NAMED_ASSOCIATIONS = {
    "Age-volume association": {
        "x": "Age",
        "y": "Volume",
        "covariates": ["Sex"],
    },
    "Volume-activity coupling": {
        "x": "Volume",
        "y": "M10",
        "covariates": ["Age", "Sex"],
    },
}


@pytest.fixture
def association_df():
    rng = np.random.default_rng(42)
    rows = []
    for group, age_slope, activity_slope in (
        ("Control", -0.12, 0.75),
        ("MCI", -0.45, 0.20),
        ("AD", -0.75, -0.15),
    ):
        for index, age in enumerate(np.linspace(58.0, 82.0, 12)):
            sex = "Female" if index % 2 else "Male"
            volume = (
                age_slope * (age - 70.0)
                + (0.25 if sex == "Female" else 0.0)
                + rng.normal(0.0, 0.35)
            )
            activity = (
                activity_slope * volume
                + 0.025 * age
                + (0.15 if sex == "Female" else 0.0)
                + rng.normal(0.0, 0.35)
            )
            rows.append(
                {
                    "Subject": f"{group}-{index}",
                    "Diagnosis": group,
                    "Sex": sex,
                    "Age": age,
                    "Volume": volume,
                    "M10": activity,
                }
            )
    return pd.DataFrame(rows)


def _plot(source, **kwargs):
    options = {
        "associations": NAMED_ASSOCIATIONS,
        "factor": "Diagnosis",
        "group_order": GROUP_ORDER,
        "reference": "Control",
        "bootstrap_resamples": 100,
        "random_state": 17,
        "save": False,
        "return_data": True,
    }
    options.update(kwargs)
    if isinstance(source, pd.DataFrame):
        options.setdefault("group_col", "Diagnosis")
        options.setdefault("subject_col", "Subject")
    return plot_association_coefficients(source, **options)


def _experiment(frame, tmp_path):
    return from_dataframe(
        frame,
        group_col="Diagnosis",
        subject_col="Subject",
        fig_path=tmp_path / "figures",
        data_path=tmp_path / "data",
    )


def _axis_text(fig):
    return "\n".join(text.get_text() for text in fig.axes[0].texts)


def test_named_mapping_returns_joint_plot_data(association_df):
    result = _plot(association_df)
    assert isinstance(result["figure"], Figure)
    assert result["figure"].axes[0].get_ylabel() == "Coefficient (standardized beta)"
    assert result["coefficients"].shape[0] == 6
    assert result["interactions"].shape[0] == 4
    assert result["coefficients"]["association"].drop_duplicates().tolist() == list(
        NAMED_ASSOCIATIONS
    )
    assert result["joint_test"]["df"] == 4
    assert result["bootstrap"] == {
        "requested": 100,
        "valid": 100,
        "random_state": 17,
    }
    plt.close(result["figure"])


def test_show_values_switch_and_side_offset_labels(association_df):
    labelled = _plot(association_df, show_stats_summary=False)
    label_values = {
        f"{estimate:+.2f}" for estimate in labelled["coefficients"]["estimate"]
    }
    labels = [
        text
        for text in labelled["figure"].axes[0].texts
        if text.get_text() in label_values
    ]
    assert len(labels) == len(label_values)
    assert {text.get_text() for text in labels} == label_values
    assert {text.get_ha() for text in labels} <= {"left", "right"}
    for text in labels:
        x_offset, y_offset = text.xyann
        assert abs(x_offset) >= 22
        assert y_offset != 0
    plt.close(labelled["figure"])

    hidden = _plot(
        association_df,
        show_values=False,
        show_stats_summary=False,
    )
    hidden_text = _axis_text(hidden["figure"])
    for label in label_values:
        assert label not in hidden_text
    plt.close(hidden["figure"])


def test_shared_complete_case_cohort_is_used_for_every_model(association_df):
    frame = association_df.copy()
    frame.loc[frame["Subject"].eq("AD-0"), "M10"] = np.nan
    result = _plot(frame)
    counts = result["coefficients"].pivot(
        index="association", columns="group", values="n"
    )
    assert counts.loc[:, "AD"].tolist() == [11, 11]
    assert counts.loc[:, "Control"].tolist() == [12, 12]
    plt.close(result["figure"])


def test_raw_dataframe_and_dataframe_experiment_paths(association_df, tmp_path):
    raw = _plot(association_df)
    adapted = _plot(_experiment(association_df, tmp_path))
    np.testing.assert_allclose(
        raw["coefficients"]["estimate"],
        adapted["coefficients"]["estimate"],
    )
    assert isinstance(_experiment(association_df, tmp_path), DataFrameExperiment)
    plt.close(raw["figure"])
    plt.close(adapted["figure"])


def test_miniexperiment_and_batch_paths(association_df, tmp_path):
    input_dir = tmp_path / "mini"
    input_dir.mkdir()
    association_df.to_csv(input_dir / "Data.csv", index=False)
    conditions = (
        ConditionBuilder("Diagnosis")
        .add("Control", color="black")
        .add("MCI", color="blue")
        .add("AD", color="orange")
        .build()
    )
    mini = MiniExperiment("Human", str(input_dir), subject_column="Subject")
    batch = Batch("human", [mini], conditions, str(tmp_path / "batch"))
    batch.processData(import_images=False, progress=False)

    mini_result = _plot(mini)
    batch_result = _plot(batch)
    np.testing.assert_allclose(
        mini_result["coefficients"]["estimate"],
        batch_result["coefficients"]["estimate"],
    )
    plt.close(mini_result["figure"])
    plt.close(batch_result["figure"])


def test_list_specs_infer_labels_and_honour_column_labels(association_df, tmp_path):
    associations = [
        {"x": "Age", "y": "Volume", "covariates": ["Sex"]},
        {"x": "Volume", "y": "M10", "covariates": ["Age", "Sex"]},
    ]
    result = _plot(
        _experiment(association_df, tmp_path),
        associations=associations,
        column_labels={
            "Age": "Age (years)",
            "Volume": "HT volume",
            "M10": "Active-phase activity",
        },
    )
    legend_labels = [text.get_text() for text in result["figure"].axes[0].get_legend().texts]
    assert legend_labels == [
        "Age (years) -> HT volume",
        "HT volume -> Active-phase activity",
    ]
    assert result["figure"].axes[0].get_legend()._ncols == 1
    assert set(result["coefficients"]["x"]) == {"Age", "Volume"}
    assert set(result["coefficients"]["y"]) == {"Volume", "M10"}
    plt.close(result["figure"])


def test_raw_slope_and_ols_interval_modes(association_df):
    result = _plot(association_df, value="slope", ci_method="ols")
    coefficients = result["coefficients"]
    assert coefficients["value"].eq("slope").all()
    assert coefficients["ci_method"].eq("ols").all()
    assert result["figure"].axes[0].get_ylabel() == "Coefficient (raw slope)"
    assert np.isfinite(coefficients[["estimate", "ci_low", "ci_high"]]).all().all()
    plt.close(result["figure"])


def test_stats_summary_is_exact_and_removable(association_df):
    shown = _plot(association_df, show_stats_summary=True)
    hidden = _plot(association_df, show_stats_summary=False)
    text = _axis_text(shown["figure"])
    assert "Models:" in text
    assert "Age-volume association:" in text
    assert "Volume ~ Age * Diagnosis + Sex" in text
    assert "Volume-activity coupling:" in text
    assert "M10 ~ Volume * Diagnosis + Age + Sex" in text
    assert "Joint Wald: chi-square(4)=" in text
    assert "p=" in text
    assert "n=" in text
    assert "delta=" in text
    assert "Joint Wald" not in _axis_text(hidden["figure"])
    plt.close(shown["figure"])
    plt.close(hidden["figure"])


def test_roi_and_specificity_queues(association_df, tmp_path):
    exp = from_dataframe(
        association_df,
        group_col="Diagnosis",
        subject_col="Subject",
        fig_path=tmp_path / "figures",
        summaries={"SCN": association_df, "PVN": association_df.copy()},
    )
    roi_result = _plot(exp, roi=["SCN", "PVN"], return_data=False)
    assert set(roi_result) == {"SCN", "PVN"}
    assert all(isinstance(figure, Figure) for figure in roi_result.values())

    specificity_result = _plot(
        exp,
        specificity=[{"Sex": ["Female"]}, {"Sex": ["Male"]}],
        roi="SCN",
        min_n=4,
        return_data=False,
    )
    assert len(specificity_result) == 2
    assert all(isinstance(figure, Figure) for figure in specificity_result.values())
    for figure in [*roi_result.values(), *specificity_result.values()]:
        plt.close(figure)


def test_clear_validation_errors(association_df):
    with pytest.raises(ValueError, match="No columns matched.*Missing"):
        _plot(
            association_df,
            associations=[{"x": "Missing", "y": "Volume"}],
        )
    with pytest.raises(ValueError, match="at least 100"):
        _plot(association_df, bootstrap_resamples=99)
    with pytest.raises(ValueError, match="group_order levels not found"):
        _plot(association_df, group_order=["Control", "Unknown"])


def test_report_records_and_registry_classification(association_df):
    report.start()
    try:
        result = _plot(association_df)
        records = report.collect()
    finally:
        report.collect()
    assert len([record for record in records if record["kind"] == "correlation"]) == 6
    models = [record for record in records if record["kind"] == "linear_model"]
    assert len(models) == 3
    by_outcome = {record["dependent_variable"]: record for record in models}
    assert by_outcome["Volume"]["formula"] == "Volume ~ Age * Diagnosis + Sex"
    assert by_outcome["Volume"]["covariates"] == ["Sex"]
    assert by_outcome["M10"]["formula"] == "M10 ~ Volume * Diagnosis + Age + Sex"
    assert by_outcome["M10"]["covariates"] == ["Age", "Sex"]
    assert models[-1]["component_models"] == [
        {
            "association": "Age-volume association",
            "formula": "Volume ~ Age * Diagnosis + Sex",
            "x": "Age",
            "y": "Volume",
            "group": "Diagnosis",
            "covariates": ["Sex"],
        },
        {
            "association": "Volume-activity coupling",
            "formula": "M10 ~ Volume * Diagnosis + Age + Sex",
            "x": "Volume",
            "y": "M10",
            "group": "Diagnosis",
            "covariates": ["Age", "Sex"],
        },
    ]
    assert models[-1]["p"] == pytest.approx(result["joint_test"]["p"])
    assert PLOT_REGISTRY["association_coefficients"] == "plot_association_coefficients"
    assert describe_status("association_coefficients") == "covered"
    plt.close(result["figure"])
