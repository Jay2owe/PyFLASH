# Marker Tables

## Summary

Marker tables are row-level measurement tables stored in an object's `.data`
dictionary. Each value in `.data` is a marker-like wrapper with a `.df`
DataFrame. These tables preserve the object, cell, ROI intensity, behaviour,
attribute, or ROI-property rows that later get summarized into `.summary`.

Unlike the summary table, marker tables are not one row per subject. A single
subject can have many object rows, cell rows, ROI intensity rows, or behaviour
rows.

## Where It Appears

- `Experiment.data["GFAP"].df` for object or cell marker measurements.
- `Experiment.data["GFAP_ROI"].df` for ROI intensity measurements.
- `Experiment.data["SCN ROI Properties"].df` for ROI property tables.
- `Experiment.data["ROIs"].df` and `Experiment.data["ROIs To Draw"].df` for ROI zip coordinate records.
- `MiniExperiment.data["table-name"].df` for flat CSV imports.
- `DataFrameExperiment.data["name"].df` when table-backed data is supplied through `data={...}`.

## Required Fields

The minimum useful fields depend on the marker family, but these fields are
stable in normalized PyFLASH tables:

| Field | Meaning |
|---|---|
| `AnimalName` | Subject identifier, normalized from source names such as `Animal Name` when needed. |
| Marker metric columns | Numeric or categorical measurements. In folder-backed imports these are commonly prefixed with the marker name. |

Marker tables used for ROI-aware processing normally also need:

| Field | Meaning |
|---|---|
| `Region` | Concrete ROI or region instance, such as `SCN1`. |
| `ROI` | ROI label from the source table. It may be a concrete value such as `SCN1` or a base value such as `SCN`; summary building derives ROI bases when needed. |
| `Hemisphere` | Normalized hemisphere label when available. |

## Optional Fields

Common optional fields include:

| Field or Pattern | Meaning |
|---|---|
| `Condition` | Added after conditions are applied. |
| Factor columns | Columns such as `Diagnosis` or `Sex`, also added from conditions when possible. |
| `ImageROI` | Image panel label aligned to the ROI drawing order. |
| `ROINameRaw` | Original ROI label before normalization. |
| `Label` | Object or ROI label from the ImageJ export. |
| `<marker>_Volume`, `<marker>_Surface`, `<marker>_IntDen`, `<marker>_MeanIntDen` | Per-row object morphology or intensity measurements. |
| `<marker>_XM`, `<marker>_YM`, `<marker>_RawXM`, `<marker>_RawYM` | Per-object coordinates. |
| `<marker>_DistToClosest_<other>`, `<marker>_DistToVentricle` | Distance measurements added by processing. |
| `<marker>_VolColoc...`, `<marker>_CPCColoc...`, `<marker>_Contains...`, `<marker>_Any...` | Colocalisation, containment, or association measurements. The exact prefixes depend on the imported pipeline output. |

PyFLASH drops several generated helper columns during import when it needs to
recompute them consistently. Treat row-level metric columns as data-dependent.

## Example

```text
| AnimalName | Condition | Region | ROI | ImageROI | GFAP_Volume | GFAP_IntDen | GFAP_CPCContains_DAPI |
|---|---|---|---|---|---:|---:|---:|
| Mouse_01 | Control | SCN1 | SCN1 | LHSCN | 10.2 | 450.0 | 0 |
| Mouse_01 | Control | SCN1 | SCN1 | LHSCN | 8.7 | 390.5 | 1 |
| Mouse_02 | AD | SCN1 | SCN1 | LHSCN | 12.1 | 520.8 | 1 |
```

For table-backed data:

```python
import pandas as pd
from PyFLASH import from_dataframe

summary = pd.DataFrame({
    "Subject": ["Mouse_01", "Mouse_02"],
    "Diagnosis": ["Control", "AD"],
    "GFAP Total": [123.4, 156.7],
})

objects = pd.DataFrame({
    "Subject": ["Mouse_01", "Mouse_01", "Mouse_02"],
    "Area": [10.0, 11.0, 20.0],
})

exp = from_dataframe(
    summary,
    group_col="Diagnosis",
    subject_col="Subject",
    data={"Objects": objects},
)
```

## Produced By

- `Experiment.importCSVs()`, which reads FLASH/ImageJ CSV and ROI zip outputs.
- `MiniExperiment.importCSVs()`, which reads a flat folder of CSV files.
- [`from_dataframe`](../functions/from_dataframe.md), when passed a `data={...}` mapping.
- Processing helpers such as closest-distance, ventricle-distance, colocalisation, and summary-building code, which can add derived columns.

## Consumed By

- `Experiment.createSummary()`, which aggregates row-level marker tables into the summary table.
- Marker-level plot functions such as [`plot_histograms`](../functions/plot_histograms.md), [`plot_locations`](../functions/plot_locations.md), and image/representative workflows that need marker names.
- Export methods that write extended data workbooks.
- ROI and distance processing helpers inside `Experiment.processData()`.

## Notes

- `.data` keys are not guaranteed to exactly match source filenames. ROI intensity tables are often keyed with `_ROI`, and repeated batch marker names can be disambiguated.
- `Condition` and factor columns are applied after a group list is assigned. Raw imports may not contain them yet.
- Some table types are metadata inputs rather than biological marker measurements. For example, ROI property tables and `ROIs` coordinate tables live in `.data` but should not be interpreted as marker object tables.
- Marker table rows can be much larger than summary tables. Use summary tables for subject-level statistics unless you need row-level distributions or spatial information.

## See Also

- [Markers](../object-types/markers.md)
- [Summary Table](summary-table.md)
- [ROI Tables](roi-tables.md)
- [Image Table](image-table.md)
- [Plot histograms](../functions/plot_histograms.md)
