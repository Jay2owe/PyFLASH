# MiniExperiment

## Summary

`MiniExperiment` is a lightweight subclass of [`Experiment`](experiment.md) for
a folder of ordinary CSV files. It is useful when you want flat tabular data to
behave like an experiment inside a [`Batch`](batch.md), without the full
FLASH/ImageJ marker-folder layout.

It imports each CSV file as an `Attribute` table, builds a subject-level summary
by averaging numeric columns per subject/sample, and can map factor columns to
PyFLASH groups.

## How To Create It

Create a `MiniExperiment`, then place it in a `Batch`:

```python
from PyFLASH import Batch, MiniExperiment, GroupBuilder

groups = (
    GroupBuilder("Diagnosis")
    .add("Control", short="Control", color="grey")
    .add("AD", short="AD", color="red")
    .build()
)

experiment = MiniExperiment(
    "human-table",
    "/path/to/csv-folder",
    subject_column="Subject ID",
    factor_mappings={
        "Diagnosis": {
            "Healthy control": "Control",
            "Dementia-AD": "AD",
        },
    },
)

batch = Batch("human-batch", [experiment], groups, "/path/to/output-folder")
batch.processData(import_images=False)
```

The CSV folder can contain files such as:

```text
/path/to/csv-folder/
  Data.csv
  ExtraMeasurements.csv
```

Each CSV needs a subject column. If the subject column is not named
`AnimalName`, pass `subject_column=...`.

## Important Attributes

| Attribute | Meaning |
|---|---|
| `subject_column` | Optional source column used as the subject identifier. If omitted, common names such as `AnimalName`, `Animal Name`, `Animal ID`, `ID`, `Id`, and `id` are tried. Legacy alias: `animal_column`. |
| `factor_mappings` | Optional mapping that converts source factor values to PyFLASH group names. |
| `data_layout` | Always set to `"mini"` after construction. |
| `data` | Dictionary of CSV-derived `Attribute` tables. Each value has a `.df` DataFrame. |
| `summary` | Subject-level summary table built from the flat CSV data. |
| `summaries` | Dictionary containing the primary `"SCN"` summary. |
| `condition_list`, `conditions`, `factor`, `factorDict` | Group metadata attached by `Batch.processData()` or `set_condition_list()`. `conditions` is the legacy/internal attribute name. |
| `filePath` | Folder containing the CSV files. |
| `source_root` | Same as `filePath` for mini experiments. |
| Output paths | Inherited from `Experiment` and set under the mini experiment folder or batch output folder depending on workflow. |

## Common Methods

| Method | Use |
|---|---|
| `importCSVs(progress=True)` | Import all CSV files in the folder except `Condition Labels.csv`. |
| `createSummary(progress=True)` | Build a subject-level summary from imported CSV tables. |
| `set_condition_list(condition_list)` | Map group and factor columns using the supplied group list. |
| `processData(import_images=True, progress=True)` | Import CSVs, build the summary, configure save paths, and optionally import images. |
| `createSavePaths()` | Inherited from `Experiment`; sets standard output path attributes. |
| `getDisplaySummary(roi_base=None)` | Inherited display helper for readable summary labels. |
| `save_csvs()` | Inherited CSV export helper. |

## Accepted By

`MiniExperiment` can be included in a `Batch` and can be passed to many
summary-first plots and helpers after it has been processed. For most analysis,
pass the surrounding `Batch`.

## Returned By

`MiniExperiment` is constructed directly:

```python
from PyFLASH import MiniExperiment

experiment = MiniExperiment("name", "/path/to/csv-folder", subject_column="ID")
```

## Examples

Flat CSV with crossed factors:

```python
from PyFLASH import Batch, GroupBuilder, MiniExperiment

diagnosis = (
    GroupBuilder("Diagnosis")
    .add("Control", "Control", color="grey")
    .add("AD", "AD", color="red")
    .build()
)
sex = (
    GroupBuilder("Sex")
    .add("Female", "Female", style="hollow")
    .add("Male", "Male")
    .build()
)
groups = GroupBuilder.cross(diagnosis, sex).build()

experiment = MiniExperiment(
    "human",
    "/path/to/csv-folder",
    subject_column="ID",
    factor_mappings={
        "Diagnosis": {"Healthy control": "Control", "Dementia-AD": "AD"},
        "Sex": {"female": "Female", "male": "Male"},
    },
)

batch = Batch("human", [experiment], groups, "/path/to/output-folder")
batch.processData(import_images=False)

print(batch.summary[["AnimalName", "Diagnosis", "Sex", "Condition"]])
```

Inspect the imported CSV table:

```python
data = batch.data["Data"].df
print(data.head())
```

## Notes

- `MiniExperiment` is flat-table oriented. It does not classify ImageJ
  `Objects`, `Attributes`, `ROI Intensities`, and `ROIs` folders the way
  `Experiment.importCSVs()` does.
- Empty rows are dropped during CSV preparation.
- Numeric subject identifiers such as `1.0` are normalized to string form such
  as `"1"`.
- If all factor columns in the group list are present, `MiniExperiment`
  derives the combined `Condition` value from those factors.

## See Also

- [Experiment](experiment.md)
- [Batch](batch.md)
- [Groups](conditions.md)
- [First table batch](../getting-started/first-table-batch.md)
- [Build groups](../workflows/build-conditions.md)
