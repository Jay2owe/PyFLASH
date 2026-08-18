from types import SimpleNamespace
import glob
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from PyFLASH.modelling import run_linear_model_pipeline
from PyFLASH.pipeline import linear_model
from PyFLASH import pipeline_montage as pm
from PyFLASH import report
from PyFLASH.plotting import (
    _linear_model_adjusted_means_figure,
    plot_linear_model_adjusted_means,
    plot_linear_model_coefficient_forest,
)
from PyFLASH.spec import PLOT_REGISTRY, _resolve_func, describe_status


def _model_batch(tmp_path):
    rows = []
    diagnoses = ["Control", "MCI", "AD"]
    sexes = ["Female", "Male"]
    for i in range(60):
        diagnosis = diagnoses[i % len(diagnoses)]
        sex = sexes[(i // len(diagnoses)) % len(sexes)]
        age = 58 + ((i * 7) % 27)
        sleep = 1 if i % 5 == 0 else 0
        if i % 7 == 0:
            meds = "lorazepam"
        elif i % 11 == 0:
            meds = "donepezil"
        else:
            meds = np.nan

        diag_effect = {"Control": 0.0, "MCI": -8.0, "AD": -28.0}[diagnosis]
        sex_effect = 4.0 if sex == "Male" else 0.0
        med_any = 0.0 if pd.isna(meds) else 1.0
        noise = (i % 4) * 0.25
        total = 220.0 + diag_effect + sex_effect - 6.0 * sleep + 1.2 * age + 3.0 * med_any + noise
        amp = 40.0 + (diag_effect * 0.15) + 0.4 * age + noise
        rows.append({
            "AnimalName": f"A{i:02d}",
            "Diagnosis": diagnosis,
            "Sex": sex,
            "Age": age,
            "sleeptreatment": sleep,
            "meds": meds,
            "Totalcounts": total,
            "Amplitude": amp,
        })
    fig_path = tmp_path / "Python Figures"
    os.makedirs(fig_path, exist_ok=True)
    return SimpleNamespace(
        summary=pd.DataFrame(rows),
        data_path=str(tmp_path),
        fig_path=str(fig_path),
        condition_list=[],
    )


def _marginal_model_batch(tmp_path):
    rows = []
    cells = [
        ("Control", "Female", 9, 10.0),
        ("Control", "Male", 1, 20.0),
        ("AD", "Female", 4, 30.0),
        ("AD", "Male", 6, 50.0),
    ]
    idx = 0
    for diagnosis, sex, count, base in cells:
        for rep in range(count):
            rows.append({
                "AnimalName": f"M{idx:02d}",
                "Diagnosis": diagnosis,
                "Sex": sex,
                "NumericObject": str(50 + idx),
                "Unused": f"unused-{idx % 2}",
                "Outcome": base + 0.05 * (rep % 3),
            })
            idx += 1
    fig_path = tmp_path / "Python Figures"
    os.makedirs(fig_path, exist_ok=True)
    return SimpleNamespace(
        summary=pd.DataFrame(rows),
        data_path=str(tmp_path),
        fig_path=str(fig_path),
        condition_list=[],
    )


def test_linear_model_pipeline_registered_and_covered():
    assert "linear_model_pipeline" in PLOT_REGISTRY
    assert _resolve_func(PLOT_REGISTRY["linear_model_pipeline"]) is linear_model
    assert describe_status("linear_model_pipeline") == "covered"
    assert _resolve_func(PLOT_REGISTRY["linear_model_adjusted_means"]) is plot_linear_model_adjusted_means
    assert describe_status("linear_model_adjusted_means") == "covered"
    assert _resolve_func(PLOT_REGISTRY["linear_model_coefficient_forest"]) is plot_linear_model_coefficient_forest
    assert describe_status("linear_model_coefficient_forest") == "covered"


def test_linear_model_pipeline_saves_adjusted_means_and_plots(tmp_path):
    batch = _model_batch(tmp_path)

    result = linear_model(
        batch,
        dependent_variables=["Total counts", "Amplitude"],
        group="Diagnosis",
        predictors=["Sex", "sleep treatment", "Age"],
        categorical=["Sex"],
        reference_levels={"Diagnosis": "Control"},
        interactions=[("Diagnosis", "Sex")],
        medication_columns=["meds"],
        medication_mode="both",
        medication_min_count=2,
        run_label="adjusted_pipeline",
        if_exists="overwrite",
        save=True,
        verbose=False,
    )

    assert result["pipeline"] == "linear_model"
    assert result["group"] == "Diagnosis"
    assert result["predictors"] == ["Sex", "sleeptreatment", "Age"]
    assert result["covariates"] == ["Sex", "sleeptreatment", "Age"]
    assert result["model_terms"][:2] == ["Diagnosis", "Sex"]
    assert set(result["model_summaries"]["dependent_variable"]) == {"Totalcounts", "Amplitude"}
    assert result["n_adjusted_means"] == 6
    assert set(result["adjusted_means_table"]["group"]) == {"Control", "MCI", "AD"}
    assert "meds_any" in result["medication_predictors"]

    fig_dir = tmp_path / "Python Figures" / "Linear Model Pipeline" / "adjusted_pipeline"
    out = Path(result["data_dir"])
    adjusted_dir = fig_dir / "Adjusted Means"
    assert out == fig_dir
    assert Path(result["adjusted_means_dir"]) == adjusted_dir
    assert (out / "linear_model_coefficients.csv").exists()
    assert (out / "linear_model_summaries.csv").exists()
    assert (out / "linear_model_metadata.csv").exists()
    assert not (out / "linear_model_adjusted_means.csv").exists()
    assert not (out / "linear_model_adjusted_mean_comparisons.csv").exists()
    assert (adjusted_dir / "linear_model_adjusted_means.csv").exists()
    assert (adjusted_dir / "linear_model_adjusted_mean_comparisons.csv").exists()
    assert (out / "manifest.json").exists()
    assert result["n_adjusted_mean_comparisons"] == 6
    assert set(result["adjusted_mean_comparisons"]["comparison"]) == {
        "1-2", "2-3", "1-3",
    }
    assert set(result["adjusted_mean_comparisons"]["p_adjust_method"]) == {"holm"}
    assert result["adjusted_mean_comparisons"]["p_adjusted"].notna().all()

    assert (fig_dir / "Coefficient Forest.svg").exists()
    assert (fig_dir / f"{pm.DEFAULT_MONTAGE_FILENAME}.png").exists()
    adjusted_svgs = glob.glob(str(adjusted_dir / "*.svg"))
    assert len(adjusted_svgs) == 2
    svg_text = Path(adjusted_svgs[0]).read_text(encoding="utf-8")
    assert "Test: Linear model" in svg_text
    assert "Post-hoc: Adjusted mean contrasts" in svg_text
    assert "Control vs MCI" in svg_text
    assert "Left slot: raw subject values with mean +/- SEM" in svg_text
    assert "right slot: adjusted mean with 95% CI" in svg_text
    assert "Bracket labels: adjusted p" in svg_text
    assert "Correction: Holm across" in svg_text

    fig = _linear_model_adjusted_means_figure(
        result["adjusted_means_table"],
        "Totalcounts",
        "Diagnosis",
        group_order=["Control", "MCI", "AD"],
        comparisons=result["adjusted_mean_comparisons"],
    )
    try:
        # Adjusted means render as points, not bars, so there must be no visible
        # bar/background patch. The comparison-line renderer adds one invisible,
        # gid-tagged sizing anchor (reserves a fixed tight-SVG height across
        # ns/star glyphs); that is not a data mark, so exclude it.
        visible_patches = [
            p for p in fig.axes[0].patches
            if p.get_gid() != "pyflash-comparison-height-anchor"
        ]
        assert not visible_patches
    finally:
        import matplotlib.pyplot as plt
        plt.close(fig)


def test_linear_model_pipeline_supports_emm_and_observed_profiles(tmp_path):
    batch = _marginal_model_batch(tmp_path)
    cell_means = batch.summary.groupby(["Diagnosis", "Sex"])["Outcome"].mean()
    sex_weights = batch.summary["Sex"].value_counts(normalize=True)

    mean_mode = linear_model(
        batch,
        dependent_variables=["Outcome"],
        group="Diagnosis",
        predictors=["Sex"],
        categorical=["Sex"],
        reference_levels={"Diagnosis": "Control"},
        interactions=[("Diagnosis", "Sex")],
        covariate_profile="mean_mode",
        adjusted_mean_p_adjust="none",
        save=False,
        verbose=False,
    )["adjusted_means_table"].set_index("group")
    assert mean_mode.loc["Control", "adjusted_mean"] == pytest.approx(
        cell_means.loc[("Control", "Female")]
    )

    emm = linear_model(
        batch,
        dependent_variables=["Outcome"],
        group="Diagnosis",
        predictors=["Sex"],
        categorical=["Sex"],
        reference_levels={"Diagnosis": "Control"},
        interactions=[("Diagnosis", "Sex")],
        covariate_profile="emm",
        adjusted_mean_weights="equal",
        adjusted_mean_p_adjust="none",
        save=False,
        verbose=False,
    )["adjusted_means_table"].set_index("group")
    assert set(emm["covariate_profile"]) == {"reference_grid"}
    assert set(emm["adjusted_mean_weights"]) == {"equal"}
    assert set(emm["reference_grid_rows"]) == {2}
    assert set(emm["reference_grid_columns"]) == {"Sex"}
    assert emm.loc["Control", "adjusted_mean"] == pytest.approx(
        (cell_means.loc[("Control", "Female")] + cell_means.loc[("Control", "Male")]) / 2.0
    )
    assert emm.loc["AD", "adjusted_mean"] == pytest.approx(
        (cell_means.loc[("AD", "Female")] + cell_means.loc[("AD", "Male")]) / 2.0
    )

    weighted_emm = linear_model(
        batch,
        dependent_variables=["Outcome"],
        group="Diagnosis",
        predictors=["Sex"],
        categorical=["Sex"],
        reference_levels={"Diagnosis": "Control"},
        interactions=[("Diagnosis", "Sex")],
        covariate_profile="reference_grid",
        adjusted_mean_weights="observed",
        adjusted_mean_p_adjust="none",
        save=False,
        verbose=False,
    )["adjusted_means_table"].set_index("group")
    assert set(weighted_emm["covariate_profile"]) == {"reference_grid"}
    assert set(weighted_emm["adjusted_mean_weights"]) == {"observed"}
    assert weighted_emm.loc["Control", "adjusted_mean"] == pytest.approx(
        cell_means.loc[("Control", "Female")] * sex_weights["Female"]
        + cell_means.loc[("Control", "Male")] * sex_weights["Male"]
    )
    assert weighted_emm.loc["AD", "adjusted_mean"] == pytest.approx(
        cell_means.loc[("AD", "Female")] * sex_weights["Female"]
        + cell_means.loc[("AD", "Male")] * sex_weights["Male"]
    )

    observed = linear_model(
        batch,
        dependent_variables=["Outcome"],
        group="Diagnosis",
        predictors=["Sex"],
        categorical=["Sex"],
        reference_levels={"Diagnosis": "Control"},
        interactions=[("Diagnosis", "Sex")],
        covariate_profile="observed",
        adjusted_mean_p_adjust="none",
        save=False,
        verbose=False,
    )["adjusted_means_table"].set_index("group")
    assert set(observed["covariate_profile"]) == {"observed"}
    assert set(observed["reference_grid_rows"]) == {len(batch.summary)}
    assert set(observed["reference_grid_columns"]) == {"Sex"}
    assert observed.loc["Control", "adjusted_mean"] == pytest.approx(
        cell_means.loc[("Control", "Female")] * sex_weights["Female"]
        + cell_means.loc[("Control", "Male")] * sex_weights["Male"]
    )
    assert observed.loc["AD", "adjusted_mean"] == pytest.approx(
        cell_means.loc[("AD", "Female")] * sex_weights["Female"]
        + cell_means.loc[("AD", "Male")] * sex_weights["Male"]
    )
    assert observed.loc["AD", "adjusted_mean"] != pytest.approx(
        emm.loc["AD", "adjusted_mean"]
    )

    numeric_object = linear_model(
        batch,
        dependent_variables=["Outcome"],
        group="Diagnosis",
        predictors=["Sex", "NumericObject"],
        categorical="auto",
        reference_levels={"Diagnosis": "Control"},
        covariate_profile="emm",
        save=False,
        verbose=False,
    )
    assert set(numeric_object["categorical"]) == {"Diagnosis", "Sex"}
    numeric_object_means = numeric_object["adjusted_means_table"]
    assert set(numeric_object_means["reference_grid_rows"]) == {2}
    assert set(numeric_object_means["reference_grid_columns"]) == {"Sex"}


def test_linear_model_adjusted_means_plot_prefers_adjusted_p_values():
    adjusted = pd.DataFrame([
        {
            "dependent_variable": "Outcome",
            "group_col": "Diagnosis",
            "group": "Control",
            "adjusted_mean": 10.0,
            "ci_low": 9.0,
            "ci_high": 11.0,
        },
        {
            "dependent_variable": "Outcome",
            "group_col": "Diagnosis",
            "group": "AD",
            "adjusted_mean": 14.0,
            "ci_low": 13.0,
            "ci_high": 15.0,
        },
    ])
    comparisons = pd.DataFrame([
        {
            "dependent_variable": "Outcome",
            "comparison": "1-2",
            "p_value": 0.001,
            "p_adjusted": 0.5,
            "p_adjust_method": "holm",
        }
    ])

    fig = _linear_model_adjusted_means_figure(
        adjusted,
        "Outcome",
        "Diagnosis",
        group_order=["Control", "AD"],
        comparisons=comparisons,
    )
    try:
        text = "\n".join(t.get_text() for ax in fig.axes for t in ax.texts)
        assert "Post-hoc: Adjusted mean contrasts (holm)" in text
        assert "Bracket labels: adjusted p" in text
        assert "Correction: Holm across 1 contrast" in text
        assert "Control vs AD: adj p=0.5 (raw p=0.001)" in text
        assert "Control vs AD: p=0.001" not in text
    finally:
        import matplotlib.pyplot as plt
        plt.close(fig)


def test_public_linear_model_plots_accept_result_dict_and_csv(tmp_path):
    batch = _model_batch(tmp_path)
    result = linear_model(
        batch,
        dependent_variables=["Total counts", "Amplitude"],
        group="Diagnosis",
        predictors=["Sex", "Age"],
        categorical=["Sex"],
        reference_levels={"Diagnosis": "Control"},
        save=False,
        verbose=False,
    )

    adjusted = plot_linear_model_adjusted_means(
        result,
        dependent_variable="Totalcounts",
        save=True,
        save_path=tmp_path,
        save_name="Adjusted Public",
        return_data=True,
    )
    assert Path(adjusted["paths"]["Totalcounts"]).exists()

    coeff = plot_linear_model_coefficient_forest(
        result,
        dependent_variables=["Totalcounts"],
        save=True,
        save_path=tmp_path,
        save_name="Coefficient Public",
        return_data=True,
    )
    assert Path(coeff["path"]).exists()

    fig = plot_linear_model_adjusted_means(
        result,
        dependent_variable="Totalcounts",
        show_stats_summary=True,
        save=False,
    )
    try:
        text = "\n".join(t.get_text() for ax in fig.axes for t in ax.texts)
        assert "Adjusted for: Sex, Age" in text
    finally:
        import matplotlib.pyplot as plt
        plt.close(fig)

    means_csv = tmp_path / "adjusted_means.csv"
    comparisons_csv = tmp_path / "adjusted_comparisons.csv"
    result["adjusted_means_table"].to_csv(means_csv, index=False)
    result["adjusted_mean_comparisons"].to_csv(comparisons_csv, index=False)
    csv_path = plot_linear_model_adjusted_means(
        path=means_csv,
        comparisons_path=comparisons_csv,
        dependent_variable="Amplitude",
        group="Diagnosis",
        group_order=["Control", "MCI", "AD"],
        save=True,
        save_path=tmp_path,
        save_name="Adjusted From CSV",
    )
    assert Path(csv_path).exists()


def test_linear_model_coefficient_forest_groups_terms_by_dependent_variable():
    coefficients = pd.DataFrame([
        {
            "dependent_variable": "First",
            "term": "C(Diagnosis, Treatment(reference='Control'))[T.MCI]",
            "estimate": 1.0,
            "ci_low": 0.2,
            "ci_high": 1.8,
            "p_value": 0.2,
        },
        {
            "dependent_variable": "Second",
            "term": "C(Diagnosis, Treatment(reference='Control'))[T.MCI]",
            "estimate": -2.0,
            "ci_low": -3.0,
            "ci_high": -1.0,
            "p_value": 0.01,
        },
        {
            "dependent_variable": "First",
            "term": "Age",
            "estimate": 0.5,
            "ci_low": -0.1,
            "ci_high": 1.1,
            "p_value": 0.4,
        },
        {
            "dependent_variable": "Second",
            "term": "C(Sex)[T.Male]",
            "estimate": 0.1,
            "ci_low": -0.3,
            "ci_high": 0.5,
            "p_value": 0.8,
        },
    ])

    fig = plot_linear_model_coefficient_forest(
        coefficients=coefficients,
        title="Linear model coefficients",
        save=False,
    )
    try:
        ax = fig.axes[0]
        top_to_bottom = [t.get_text() for t in ax.get_yticklabels()][::-1]
        assert top_to_bottom == [
            "First: Diagnosis: MCI",
            "First: Age",
            "Second: Diagnosis: MCI",
            "Second: Sex: Male",
        ]
        assert all("C(" not in label for label in top_to_bottom)
        assert all("Treatment(" not in label for label in top_to_bottom)
        assert ax.title.get_fontweight() == "normal"
        assert ax.xaxis.label.get_fontweight() == "normal"
        assert ax.title.get_position()[1] >= 1.0
    finally:
        import matplotlib.pyplot as plt
        plt.close(fig)


def test_linear_model_adjusted_means_plot_overlays_raw_model_rows(tmp_path):
    batch = _model_batch(tmp_path)
    result = linear_model(
        batch,
        dependent_variables=["Total counts"],
        group="Diagnosis",
        predictors=["Sex", "Age"],
        categorical=["Sex"],
        reference_levels={"Diagnosis": "Control"},
        save=False,
        verbose=False,
    )

    fig = plot_linear_model_adjusted_means(
        result,
        dependent_variable="Totalcounts",
        show_stats_summary=True,
        save=False,
    )
    try:
        ax = fig.axes[0]
        raw_collections = [
            collection for collection in ax.collections
            if collection.get_gid() == "pyflash-linear-model-raw-points"
        ]
        raw_n = sum(len(collection.get_offsets()) for collection in raw_collections)
        assert raw_n == len(result["model_data"]["Totalcounts"])
        assert len(raw_collections) == 3
        adjusted_collections = [
            collection for collection in ax.collections
            if collection.get_gid() == "pyflash-linear-model-adjusted-mean"
        ]
        assert len(adjusted_collections) == 3
        raw_mean_markers = [
            collection for collection in ax.collections
            if collection.get_gid() == "pyflash-linear-model-raw-mean-sem"
        ]
        assert len(raw_mean_markers) == 3
        raw_centers = [
            float(collection.get_offsets()[:, 0].mean())
            for collection in raw_collections
        ]
        raw_edge_colors = [
            tuple(np.round(collection.get_edgecolors()[0], 4))
            for collection in raw_collections
        ]
        assert len(set(raw_edge_colors)) == 3
        adjusted_centers = [
            float(collection.get_offsets()[:, 0].mean())
            for collection in adjusted_collections
        ]
        assert all(adj > raw for raw, adj in zip(raw_centers, adjusted_centers))
        adjusted_ci_lines = [
            line for line in ax.lines
            if line.get_gid() == "pyflash-linear-model-adjusted-ci"
        ]
        assert len(adjusted_ci_lines) == 3
        adjusted_ci_caps = [
            line for line in ax.lines
            if line.get_gid() == "pyflash-linear-model-adjusted-ci-cap"
        ]
        assert len(adjusted_ci_caps) == 6
        raw_sem_lines = [
            line for line in ax.lines
            if line.get_gid() == "pyflash-linear-model-raw-sem"
        ]
        raw_sem_caps = [
            line for line in ax.lines
            if line.get_gid() == "pyflash-linear-model-raw-sem-cap"
        ]
        assert len(raw_sem_lines) == 3
        assert len(raw_sem_caps) == 6
        raw_sem_centers = [
            float(line.get_xdata()[0])
            for line in raw_sem_lines
        ]
        assert np.diff(adjusted_centers) == pytest.approx([0.78, 0.78])
        assert [
            adjusted - raw
            for raw, adjusted in zip(raw_sem_centers, adjusted_centers)
        ] == pytest.approx([0.32, 0.32, 0.32])
        separators = [
            line for line in ax.lines
            if line.get_gid() == "pyflash-linear-model-condition-separator"
        ]
        assert len(separators) == 2
        separator_centers = [float(line.get_xdata()[0]) for line in separators]
        for idx, sep_x in enumerate(separator_centers):
            assert adjusted_centers[idx] < sep_x < raw_sem_centers[idx + 1]
            assert separators[idx].get_color() == "#C7C7C7"
            assert separators[idx].get_linestyle() == "--"
        x_left, x_right = ax.get_xlim()
        panel_widths = [
            separator_centers[0] - x_left,
            separator_centers[1] - separator_centers[0],
            x_right - separator_centers[1],
        ]
        assert panel_widths == pytest.approx([0.78, 0.78, 0.78])
        assert [line.get_linewidth() for line in adjusted_ci_caps] == pytest.approx(
            [adjusted_ci_lines[0].get_linewidth()] * len(adjusted_ci_caps)
        )
        assert [line.get_linewidth() for line in raw_sem_caps] == pytest.approx(
            [raw_sem_lines[0].get_linewidth()] * len(raw_sem_caps)
        )
        cap_spans = [
            abs(float(line.get_xdata()[1]) - float(line.get_xdata()[0]))
            for line in [*adjusted_ci_caps, *raw_sem_caps]
        ]
        assert cap_spans == pytest.approx([0.13] * len(cap_spans))
        ci_centers = [float(line.get_xdata()[0]) for line in adjusted_ci_lines]
        assert adjusted_centers == pytest.approx(ci_centers)
        text = "\n".join(t.get_text() for axis in fig.axes for t in axis.texts)
        assert "Left slot: raw subject values with mean +/- SEM" in text
        assert "right slot: adjusted mean with 95% CI" in text
        assert "Bracket labels: adjusted p" in text
        legend_labels = [t.get_text() for t in ax.get_legend().get_texts()]
        assert "Raw subject values" in legend_labels
        assert "Raw mean +/- SEM" in legend_labels
        assert "Adjusted mean +/- 95% CI" in legend_labels
    finally:
        import matplotlib.pyplot as plt
        plt.close(fig)


def test_public_linear_model_plots_emit_report_records(tmp_path):
    batch = _model_batch(tmp_path)
    result = linear_model(
        batch,
        dependent_variables=["Total counts"],
        group="Diagnosis",
        predictors=["Sex", "Age"],
        categorical=["Sex"],
        reference_levels={"Diagnosis": "Control"},
        save=False,
        verbose=False,
    )

    report.start()
    try:
        fig = plot_linear_model_adjusted_means(
            result,
            dependent_variable="Totalcounts",
            save=False,
        )
        records = report.collect()
    finally:
        if report.is_active():
            report.collect()
        import matplotlib.pyplot as plt
        plt.close(fig)

    assert len(records) == 1
    rec = records[0]
    assert rec["kind"] == "linear_model"
    assert rec["dependent_variable"] == "Totalcounts"
    assert rec["group"] == "Diagnosis"
    assert set(rec["adjusted_means"]) == {"Control", "MCI", "AD"}


def test_linear_model_pipeline_emits_report_records(tmp_path):
    batch = _model_batch(tmp_path)

    report.start()
    try:
        linear_model(
            batch,
            dependent_variables=["Total counts"],
            group="Diagnosis",
            predictors=["Sex", "Age"],
            categorical=["Sex"],
            reference_levels={"Diagnosis": "Control"},
            save=False,
            verbose=False,
        )
        records = report.collect()
    finally:
        if report.is_active():
            report.collect()

    assert len(records) == 1
    rec = records[0]
    assert rec["kind"] == "linear_model"
    assert rec["dependent_variable"] == "Totalcounts"
    assert rec["group"] == "Diagnosis"
    assert rec["predictors"] == ["Sex", "Age"]
    assert set(rec["adjusted_means"]) == {"Control", "MCI", "AD"}
    assert "Age" in rec["coefficients"]


def test_linear_model_pipeline_adjusts_covariates_and_saves_tables(tmp_path):
    batch = _model_batch(tmp_path)

    result = run_linear_model_pipeline(
        batch,
        dependent_variables=["Total counts", "Amplitude"],
        predictors=["Diagnosis", "Sex", "sleep treatment", "Age"],
        categorical=["Diagnosis", "Sex"],
        reference_levels={"Diagnosis": "Control"},
        interactions=[("Diagnosis", "Sex")],
        medication_columns=["meds"],
        medication_mode="both",
        medication_min_count=2,
        run_label="adjusted",
        if_exists="overwrite",
        save=True,
        return_fits=True,
        verbose=False,
    )

    coefficients = result["coefficients"]
    summaries = result["model_summaries"]

    assert set(summaries["dependent_variable"]) == {"Totalcounts", "Amplitude"}
    assert "Treatment(reference='Control')" in result["formulas"]["Totalcounts"]
    assert ":" in result["formulas"]["Totalcounts"]
    assert "meds_any" in result["medication_predictors"]
    assert any(col.startswith("meds_lorazepam") for col in result["medication_predictors"])
    assert any(col.startswith("meds_donepezil") for col in result["medication_predictors"])
    assert coefficients["q_value"].notna().any()
    assert "fits" in result and set(result["fits"]) == {"Totalcounts", "Amplitude"}

    out = tmp_path / "Modelling" / "Linear Models" / "adjusted"
    assert (out / "linear_model_coefficients.csv").exists()
    assert (out / "linear_model_summaries.csv").exists()
    assert (out / "linear_model_metadata.csv").exists()
    assert (out / "manifest.json").exists()


def test_linear_model_pipeline_versions_existing_runs(tmp_path):
    batch = _model_batch(tmp_path)
    kwargs = dict(
        dependent_variables=["Totalcounts"],
        predictors=["Diagnosis", "Age"],
        categorical=["Diagnosis"],
        reference_levels={"Diagnosis": "Control"},
        run_label="repeat",
        save=True,
        verbose=False,
    )

    first = run_linear_model_pipeline(batch, if_exists="overwrite", **kwargs)
    second = run_linear_model_pipeline(batch, if_exists="version", **kwargs)

    assert first["run_label"] == "repeat"
    assert second["run_label"] == "repeat_v2"
    assert second["output_dir"].endswith("repeat_v2")
