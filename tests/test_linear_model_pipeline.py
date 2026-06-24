from types import SimpleNamespace

import numpy as np
import pandas as pd

from PyFLASH.modelling import run_linear_model_pipeline


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
    return SimpleNamespace(summary=pd.DataFrame(rows), data_path=str(tmp_path))


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
