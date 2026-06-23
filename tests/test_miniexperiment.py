import os

from PyFLASH.batch import Batch
from PyFLASH.conditions import condition, conditionList, zipConditions, zipConditionLists
from PyFLASH.experiment import MiniExperiment


def _write_csv(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def _human_conditions():
    AD = condition("AD", "AD", "#9f1c1f", "Diagnosis")
    MCI = condition("MCI", "MCI", "#4369b2", "Diagnosis")
    Control = condition("Control", "Control", "#787a7c", "Diagnosis")
    diagnosis = conditionList([AD, MCI, Control])

    Male, Female = zipConditions(
        ["Male", "Female"],
        ["Male", "Female"],
        [None, None],
        "Sex",
    )
    sex = conditionList([Male, Female])

    ADMale, ADFemale, MCIMale, MCIFemale, ControlMale, ControlFemale = zipConditionLists(
        diagnosis,
        sex,
    )
    return conditionList([
        ADMale,
        ADFemale,
        MCIMale,
        MCIFemale,
        ControlMale,
        ControlFemale,
    ])


def test_miniexperiment_maps_flat_human_csv_conditions(tmp_path):
    _write_csv(
        tmp_path / "Data.csv",
        "\n".join([
            "ID,Diagnosis,Sex,Period (h)",
            "1,Dementia-AD,Female,24.2",
            "2,MCI-AD,Male,23.9",
            "3,Healthy control,male,23.8",
            ",,,",
        ]),
    )

    exp = MiniExperiment(
        "Human",
        str(tmp_path),
        animal_column="ID",
        factor_mappings={
            "Diagnosis": {
                "Dementia-AD": "AD",
                "MCI-AD": "MCI",
                "Healthy control": "Control",
            },
            "Sex": {
                "male": "Male",
                "female": "Female",
            },
        },
    )
    batch = Batch("human", [exp], _human_conditions(), str(tmp_path))

    batch.processData(import_images=False, progress=False)

    summary = batch.summary.sort_values("AnimalName").reset_index(drop=True)
    assert summary["AnimalName"].tolist() == ["1", "2", "3"]
    assert summary["Diagnosis"].tolist() == ["AD", "MCI", "Control"]
    assert summary["Sex"].tolist() == ["Female", "Male", "Male"]
    assert summary["Condition"].tolist() == ["ADFemale", "MCIMale", "ControlMale"]
    assert "Period(h)" in summary.columns
    assert batch.data["Data"].df["Condition"].tolist() == ["ADFemale", "MCIMale", "ControlMale"]
