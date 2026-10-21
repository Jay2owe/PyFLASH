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


@pytest.mark.parametrize("comparison_test", ["bootstrap_wald", "ols_t"])
def test_miniexperiment_and_batch_paths(association_df, tmp_path, comparison_test):
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

    mini_result = _plot(mini, comparison_test=comparison_test)
    batch_result = _plot(batch, comparison_test=comparison_test)
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
    assert "Joint bootstrap Wald: chi-square(4)=" in text
    assert "p=" in text
    assert "n=" in text
    assert "delta=" in text
    assert "Joint bootstrap Wald" not in _axis_text(hidden["figure"])
    assert "p=" not in _axis_text(hidden["figure"])
    np.testing.assert_allclose(shown["figure"].get_size_inches(), hidden["figure"].get_size_inches())
    np.testing.assert_allclose(shown["figure"].axes[0].get_position().bounds,
                               hidden["figure"].axes[0].get_position().bounds)
    assert "Group vs reference slope tests:" in text
    assert "Pooled all-group model; two-sided Wald z-tests" in text
    assert "These intervals describe slopes, not group differences." in text
    assert "model n=36" in text
    for annotation in shown["figure"].axes[0].texts:
        if "p=" in annotation.get_text():
            assert annotation.get_position()[0] > 1
    plt.close(shown["figure"])
    plt.close(hidden["figure"])


@pytest.mark.parametrize("tail", ["two", "less", "greater"])
def test_directional_comparisons_match_independent_two_group_ols(association_df, tail):
    from scipy import stats as scipy_stats
    import statsmodels.formula.api as smf
    result = _plot(association_df, comparison_test="ols_t", comparison_tail=tail)
    comparisons = result["comparisons"]
    assert comparisons["method"].eq("ols_t").all()
    assert comparisons["model_scope"].eq("two_groups").all()
    for row in comparisons.itertuples(index=False):
        pair = association_df.loc[association_df.Diagnosis.isin([row.reference, row.group])].copy()
        pair["x"] = (pair[row.x] - pair[row.x].mean()) / pair[row.x].std(ddof=0)
        pair["y"] = (pair[row.y] - pair[row.y].mean()) / pair[row.y].std(ddof=0)
        pair["patient"] = pair.Diagnosis.ne(row.reference).astype(int)
        covariates = row.covariates.split(", ")
        formula = "y ~ x * patient" + "".join(
            " + C(Sex)" if col == "Sex" else " + " + col for col in covariates if col
        )
        fit = smf.ols(formula, data=pair).fit()
        t = float(fit.tvalues["x:patient"])
        expected_p = (2 * scipy_stats.t.sf(abs(t), fit.df_resid) if tail == "two"
                      else scipy_stats.t.cdf(t, fit.df_resid) if tail == "less"
                      else scipy_stats.t.sf(t, fit.df_resid))
        assert row.t == pytest.approx(t, rel=1e-9)
        assert row.df == fit.df_resid
        assert row.p == pytest.approx(expected_p, rel=1e-9)
        assert row.n == len(pair) == 24
        assert row.estimate == pytest.approx(fit.params["x:patient"], rel=1e-9)
    text = _axis_text(result["figure"])
    assert "Separate two-group ordinary least-squares (OLS) t-tests" in text
    assert "delta uses pair scaling; plotted beta uses all groups." in text
    assert "model n=24" in text
    assert "Pooled all-group model; two-sided Wald z-tests" not in text
    assert "OLS" not in result["figure"].axes[0].get_title()
    assert "p=" not in result["figure"].axes[0].get_title()
    plt.close(result["figure"])


def test_comparison_choice_preserves_slopes_intervals_joint_and_shared_cohort(association_df, tmp_path):
    frame = association_df.copy()
    frame.loc[0, "M10"] = np.nan
    baseline = _plot(frame)
    selected = _plot(_experiment(frame, tmp_path), comparison_test="ols_t", comparison_tail="less")
    pd.testing.assert_frame_equal(baseline["coefficients"], selected["coefficients"])
    pd.testing.assert_frame_equal(baseline["interactions"], selected["interactions"])
    assert baseline["joint_test"] == selected["joint_test"]
    assert set(selected["comparisons"]["n"]) == {23}
    assert selected["comparisons"]["n_reference"].eq(11).all()
    np.testing.assert_allclose(baseline["figure"].get_size_inches(), selected["figure"].get_size_inches())
    np.testing.assert_allclose(baseline["figure"].axes[0].get_position().bounds,
                               selected["figure"].axes[0].get_position().bounds)
    plt.close(baseline["figure"])
    plt.close(selected["figure"])


def test_comparison_options_validate_before_fitting(association_df):
    with pytest.raises(ValueError, match="comparison_test"):
        _plot(association_df, comparison_test="unknown")
    with pytest.raises(ValueError, match="comparison_tail"):
        _plot(association_df, comparison_test="ols_t", comparison_tail="one")
    with pytest.raises(ValueError, match="two-sided"):
        _plot(association_df, comparison_tail="less")


def test_actual_interval_method_and_alpha_are_explained(association_df):
    result = _plot(association_df, ci_method="ols", ci_alpha=.1)
    text = _axis_text(result["figure"])
    assert "90% OLS t confidence interval" in text
    assert "95%" not in text
    # The joint/interaction tests still use bootstrap uncertainty.
    assert "Standard errors from the group-stratified bootstrap" in text
    plt.close(result["figure"])


def test_comparisons_support_other_columns_and_reference_labels(association_df):
    frame = association_df.rename(columns={
        "Diagnosis": "Arm", "Age": "Dose", "Volume": "Response", "Sex": "Batch",
    }).copy()
    frame["Arm"] = frame["Arm"].map({
        "Control": "Baseline", "MCI": "Treatment A", "AD": "Treatment B",
    })
    result = plot_association_coefficients(
        frame, associations={"Dose-response": {"x": "Dose", "y": "Response", "covariates": ["Batch"]}},
        factor="Arm", group_col="Arm", subject_col="Subject",
        group_order=["Baseline", "Treatment A", "Treatment B"], reference="Baseline",
        comparison_test="ols_t", comparison_tail="greater", bootstrap_resamples=100,
        column_labels={"Dose": "Exposure", "Response": "Measured response"},
        save=False, return_data=True,
    )
    assert result["comparisons"]["reference"].eq("Baseline").all()
    assert set(result["comparisons"]["group"]) == {"Treatment A", "Treatment B"}
    assert result["comparisons"]["n"].eq(24).all()
    text = _axis_text(result["figure"])
    assert "Measured response ~ Exposure * Arm + Batch" in text
    assert "one-sided: group slope > reference" in text
    assert result["coefficients"]["x"].eq("Dose").all()
    plt.close(result["figure"])


def test_long_sidecar_does_not_overlap_title_and_subtitle(association_df):
    result = _plot(association_df, comparison_test="ols_t", comparison_tail="less")
    fig, ax = result["figure"], result["figure"].axes[0]
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    subtitle = next(text for text in ax.texts
                    if text.get_text() == "Group-specific model slopes with confidence intervals.")
    assert not ax._left_title.get_window_extent(renderer).overlaps(subtitle.get_window_extent(renderer))
    plt.close(fig)


def test_roi_and_specificity_queues(association_df, tmp_path):
    exp = from_dataframe(
        association_df,
        group_col="Diagnosis",
        subject_col="Subject",
        fig_path=tmp_path / "figures",
        summaries={"SCN": association_df, "PVN": association_df.copy()},
    )
    roi_result = _plot(exp, roi=["SCN", "PVN"], return_data=False,
                      comparison_test="ols_t", comparison_tail="less")
    assert set(roi_result) == {"SCN", "PVN"}
    assert all(isinstance(figure, Figure) for figure in roi_result.values())

    specificity_result = _plot(
        exp,
        specificity=[{"Sex": ["Female"]}, {"Sex": ["Male"]}],
        roi="SCN",
        min_n=4,
        return_data=False,
        comparison_test="ols_t",
        comparison_tail="less",
    )
    assert len(specificity_result) == 2
    assert all(isinstance(figure, Figure) for figure in specificity_result.values())
    for figure in [*roi_result.values(), *specificity_result.values()]:
        assert "one-sided: group slope < reference" in _axis_text(figure)
        plt.close(figure)


def test_selected_comparisons_are_preserved_in_report_records(association_df):
    report.start()
    try:
        result = _plot(association_df, comparison_test="ols_t", comparison_tail="less")
        records = report.collect()
    finally:
        report.collect()
    models = [record for record in records if record["kind"] == "linear_model"]
    assert len(models) == 3
    for model in models[:-1]:
        comparisons = model["slope_comparisons"]
        assert len(comparisons) == 2
        assert all(row["method"] == "ols_t" and row["tail"] == "less" for row in comparisons)
        assert all(row["n"] == 24 for row in comparisons)
        for row in comparisons:
            selected = result["comparisons"].loc[
                result["comparisons"].association.eq(row["association"])
                & result["comparisons"].group.eq(row["group"])
            ].iloc[0]
            assert row["p"] == pytest.approx(selected.p)
        assert model["coefficients"]["interaction[MCI]"]["method"] == "pooled bootstrap-SE Wald z"
    plt.close(result["figure"])


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
