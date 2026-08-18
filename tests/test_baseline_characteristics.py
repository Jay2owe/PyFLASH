"""Tests for the registered participant-level baseline characteristics table."""

import matplotlib

matplotlib.use("Agg")

from pathlib import Path

import pandas as pd
import pytest

from PyFLASH import ConditionBuilder, from_dataframe
from PyFLASH.plotting import plot_baseline_characteristics
from PyFLASH.spec import PLOT_REGISTRY, _resolve_func, describe_status


def _experiment(tmp_path):
    df = pd.DataFrame(
        {
            "Subject": ["C1", "C2", "M1", "M2", "A1", "A2"],
            "Diagnosis": ["Control", "Control", "MCI", "MCI", "AD", "AD"],
            "ParticipantAge": [60.0, 62.0, 70.0, 72.0, 80.0, 82.0],
            "ParticipantSex": ["Female", "Male", "Female", "Male", "Female", "Male"],
            "SleepFlag": [0, 1, 1, 0, 0, 1],
        }
    )
    conditions = (
        ConditionBuilder("Diagnosis")
        .add("Control", color="black")
        .add("MCI", color="blue")
        .add("AD", color="orange")
        .build()
    )
    return from_dataframe(
        df,
        conditions=conditions,
        condition_col="Diagnosis",
        animal_col="Subject",
        fig_path=Path(tmp_path) / "figures",
        data_path=Path(tmp_path) / "data",
    )


def _columns():
    return {
        "age": "ParticipantAge",
        "sex": "ParticipantSex",
        "sleep_treatment": "SleepFlag",
    }


def test_baseline_characteristics_is_registered_and_descriptive():
    assert PLOT_REGISTRY["baseline_characteristics"] == "plot_baseline_characteristics"
    assert _resolve_func(PLOT_REGISTRY["baseline_characteristics"]).__name__ == "plot_baseline_characteristics"
    assert describe_status("baseline_characteristics") == "exempt"


def test_baseline_characteristics_saves_editable_table_with_factor_order(tmp_path):
    exp = _experiment(tmp_path)
    path = plot_baseline_characteristics(
        exp,
        columns=_columns(),
        factor="Diagnosis",
        groups=["AD", "Control", "MCI"],
        save=True,
    )
    output = Path(path)
    assert output.exists()
    assert output.parent.name == "Tables"
    svg = output.read_text(encoding="utf-8")
    assert "<text" in svg
    assert "AD" in svg and "Control" in svg and "MCI" in svg
    assert "ParticipantAge" in svg and "SleepFlag" in svg


def test_baseline_characteristics_accepts_sequence_and_specificity_queue(tmp_path):
    exp = _experiment(tmp_path)
    outputs = plot_baseline_characteristics(
        exp,
        columns=["ParticipantAge", "ParticipantSex", "SleepFlag"],
        factor="Diagnosis",
        specificity=[("ParticipantSex", "Female"), ("ParticipantSex", "Male")],
        save=True,
    )
    assert set(outputs) == {
        ("ParticipantSex", "Female"),
        ("ParticipantSex", "Male"),
    }
    assert all(Path(path).exists() for path in outputs.values())


def test_baseline_characteristics_handles_non_numeric_age_and_requires_mapping(tmp_path):
    exp = _experiment(tmp_path)
    exp.summary["ParticipantAge"] = exp.summary["ParticipantAge"].astype(object)
    exp.summary.loc[0, "ParticipantAge"] = "not recorded"
    path = plot_baseline_characteristics(exp, columns=_columns(), save=True)
    assert "NA" in Path(path).read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="requires an explicit columns mapping"):
        plot_baseline_characteristics(exp, columns=None, save=False)
