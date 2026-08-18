"""Focused coverage for grouped multi-association correlation plots."""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from matplotlib.figure import Figure
from scipy import stats

from PyFLASH import report
from PyFLASH.dataframe import from_dataframe
from PyFLASH.plotting import plot_association_correlations
from PyFLASH.spec import PLOT_REGISTRY, describe_status


GROUP_ORDER = ["Control", "MCI", "AD"]
NAMED_ASSOCIATIONS = {
    "Age-volume association": {
        "x": "Age",
        "y": "Volume",
        "covariates": [],
    },
    "Volume-activity coupling": {
        "x": "Volume",
        "y": "M10",
        "covariates": ["Age", "Sex"],
    },
}


@pytest.fixture
def association_df():
    rng = np.random.default_rng(9)
    rows = []
    for group, age_slope, activity_slope in (
        ("Control", -0.18, 0.80),
        ("MCI", -0.35, 0.15),
        ("AD", -0.70, -0.20),
    ):
        for index, age in enumerate(np.linspace(58.0, 82.0, 12)):
            sex = "Female" if index % 2 else "Male"
            volume = (
                age_slope * (age - 70.0)
                + (0.30 if sex == "Female" else 0.0)
                + rng.normal(0.0, 0.30)
            )
            activity = (
                activity_slope * volume
                + 0.03 * age
                + (0.10 if sex == "Female" else 0.0)
                + rng.normal(0.0, 0.30)
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
        "test": "spearmanr",
        "bootstrap_resamples": 100,
        "random_state": 13,
        "save": False,
        "return_data": True,
    }
    options.update(kwargs)
    if isinstance(source, pd.DataFrame):
        options.setdefault("group_col", "Diagnosis")
        options.setdefault("subject_col", "Subject")
    return plot_association_correlations(source, **options)


def _axis_text(fig):
    return "\n".join(text.get_text() for text in fig.axes[0].texts)


def test_named_mapping_returns_correlation_plot_data(association_df):
    result = _plot(association_df)
    assert isinstance(result["figure"], Figure)
    assert result["figure"].axes[0].get_ylabel() == "Spearman correlation (rho)"
    assert result["correlations"].shape[0] == 6
    assert result["contrasts"].shape[0] == 4
    assert result["heterogeneity"].shape[0] == 2
    assert result["bootstrap"]["requested"] == 100
    assert 0 < result["bootstrap"]["valid"] <= 100
    assert result["bootstrap"]["random_state"] == 13
    by_assoc = result["correlations"].drop_duplicates("association").set_index("association")
    assert by_assoc.loc["Age-volume association", "covariates"] == ""
    assert by_assoc.loc["Volume-activity coupling", "covariates"] == "Age, Sex"
    plt.close(result["figure"])


def test_stats_summary_models_and_label_offsets(association_df):
    shown = _plot(association_df, show_stats_summary=True)
    hidden = _plot(association_df, show_stats_summary=False)
    text = _axis_text(shown["figure"])
    assert "Models:" in text
    assert "Spearman rho(Age, Volume)" in text
    assert "partial Spearman rho(Volume, M10 | Age, Sex)" in text
    assert "Heterogeneity:" in text
    assert "Bootstrap:" in text
    assert "/100 valid" in text
    assert "Heterogeneity:" not in _axis_text(hidden["figure"])

    label_values = {
        f"{estimate:+.2f}" for estimate in shown["correlations"]["estimate"]
    }
    labels = [
        item
        for item in shown["figure"].axes[0].texts
        if item.get_text() in label_values
    ]
    assert len(labels) == len(shown["correlations"])
    for label in labels:
        x_offset, y_offset = label.xyann
        assert abs(x_offset) >= 22
        assert y_offset != 0
    plt.close(shown["figure"])
    plt.close(hidden["figure"])


def test_residual_then_correlation_matches_presentation_convention(association_df):
    result = _plot(
        association_df,
        covariate_adjustment="residual_then_correlation",
    )
    row = result["correlations"].loc[
        result["correlations"]["association"].eq("Volume-activity coupling")
        & result["correlations"]["group"].eq("Control")
    ].iloc[0]
    sub = association_df.loc[
        association_df["Diagnosis"].eq("Control"),
        ["Volume", "M10", "Age", "Sex"],
    ].dropna()
    design = np.column_stack(
        [
            np.ones(len(sub)),
            sub["Age"].to_numpy(dtype=float),
            sub["Sex"].eq("Male").astype(float).to_numpy(),
        ]
    )
    volume_resid = sub["Volume"].to_numpy(dtype=float) - design @ np.linalg.lstsq(
        design, sub["Volume"].to_numpy(dtype=float), rcond=None
    )[0]
    m10_resid = sub["M10"].to_numpy(dtype=float) - design @ np.linalg.lstsq(
        design, sub["M10"].to_numpy(dtype=float), rcond=None
    )[0]
    expected = stats.spearmanr(volume_resid, m10_resid)

    assert row["estimate"] == pytest.approx(expected.statistic)
    assert row["p"] == pytest.approx(expected.pvalue)
    assert row["covariate_adjustment"] == "residual_then_correlation"
    text = _axis_text(result["figure"])
    assert "Spearman rho of covariate-adjusted residuals" in text
    plt.close(result["figure"])


def test_dataframe_adapter_save_path(association_df, tmp_path):
    exp = from_dataframe(
        association_df,
        group_col="Diagnosis",
        subject_col="Subject",
        fig_path=tmp_path / "figures",
        data_path=tmp_path / "data",
    )
    result = _plot(exp, save=True)
    saved = tmp_path / "figures" / "Association Correlations" / "Association CorrelationsDiagnosis.svg"
    assert saved.exists()
    plt.close(result["figure"])


def test_report_records_and_registry_classification(association_df):
    report.start()
    try:
        result = _plot(association_df)
        records = report.collect()
    finally:
        report.collect()
    correlations = [record for record in records if record["kind"] == "correlation"]
    assert len(correlations) == 6
    by_association = {record["association"]: record for record in correlations}
    assert by_association["Age-volume association"]["covariates"] == []
    assert by_association["Age-volume association"]["formula"] == "Spearman rho(Age, Volume)"
    assert by_association["Volume-activity coupling"]["covariates"] == ["Age", "Sex"]
    assert (
        by_association["Volume-activity coupling"]["formula"]
        == "partial Spearman rho(Volume, M10 | Age, Sex)"
    )
    heterogeneity = [
        record for record in records if record["kind"] == "correlation_heterogeneity"
    ]
    assert len(heterogeneity) == 1
    assert heterogeneity[0]["component_models"][0]["covariates"] == []
    assert PLOT_REGISTRY["association_correlations"] == "plot_association_correlations"
    assert describe_status("association_correlations") == "covered"
    plt.close(result["figure"])
