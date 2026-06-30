import pandas as pd

from PyFLASH.batch import Batch
from PyFLASH.conditions import condition, conditionList


def _minimal_batch(tmp_path):
    conds = conditionList([
        condition("Control", "Control", "#787a7c", "Diagnosis"),
        condition("AD", "AD", "#9f1c1f", "Diagnosis"),
    ])
    batch = Batch.__new__(Batch)
    batch.name = "human"
    batch.filePath = str(tmp_path)
    batch.condition_list = conds
    batch.conditions = list(conds)
    batch.factor = ["Diagnosis"]
    batch.factorDict = conds.factorDict
    batch.experiment_list = []
    batch.data = {}
    batch.summary = pd.DataFrame({
        "AnimalName": ["1", "2", "3", "4"],
        "Diagnosis": ["Control", "Control", "AD", "AD"],
        "Condition": ["Control", "Control", "AD", "AD"],
        "DAPI_Count": [1.0, 2.0, 3.0, 4.0],
        "Totalcounts": [10.0, 20.0, 30.0, 40.0],
        "Volumeanterior-inferiorHT": [11.0, 12.0, 13.0, 14.0],
    })
    return batch


def test_extra_summary_export_writes_extra_columns_only(tmp_path):
    batch = _minimal_batch(tmp_path)
    batch.export_extra_summary_excel(save_path=tmp_path)

    out = tmp_path / "Extra_Summary.xlsx"
    assert out.exists()

    xl = pd.ExcelFile(out)
    assert "Extra Columns" in xl.sheet_names
    assert "Total counts" in xl.sheet_names
    assert "Volume anterior-inferior HT" in xl.sheet_names
    assert not any("DAPI Count" in sheet for sheet in xl.sheet_names)

    total = pd.read_excel(out, sheet_name="Total counts")
    assert list(total.columns) == ["Control", "AD"]
    assert len(total) == 2
    assert pd.to_numeric(total["Control"], errors="coerce").dropna().tolist() == [10.0, 20.0]
    assert pd.to_numeric(total["AD"], errors="coerce").dropna().tolist() == [30.0, 40.0]

    index = pd.read_excel(out, sheet_name="Extra Columns")
    assert list(index.columns) == ["Column", "Display Name", "Sheet"]
    assert set(index["Column"]) == {"Totalcounts", "Volumeanterior-inferiorHT"}

    report = (tmp_path / "Extra_Summary_RegexFilters.txt").read_text(encoding="utf-8")
    assert "DAPI_Count" in report
    assert "Columns covered by standard IF summary maps" in report


def test_export_all_excel_includes_extra_summary_by_default(tmp_path):
    batch = _minimal_batch(tmp_path)
    batch.export_all_excel(
        save_path=tmp_path,
        if_summary=False,
        if_extended=False,
        behaviour=False,
    )

    assert (tmp_path / "Extra_Summary.xlsx").exists()
