# Summary Table

## Summary

The summary table is the subject-level table used by most PyFLASH plots,
pipelines, exports, and model helpers. Each row normally represents one
subject or sample within one ROI base. Numeric metric columns hold per-subject
summaries such as counts, volumes, intensities, colocalisation summaries, ROI
measurements, or behaviour values.

`Experiment.summary` and `Batch.summary` are convenience views. The richer
structure is `summaries`, a dictionary keyed by ROI base such as `"SCN"`.

## Where It Appears

- [`Experiment`](../object-types/experiment.md), [`MiniExperiment`](../object-types/mini-experiment.md), and [`DataFrameExperiment`](../object-types/dataframe-experiment.md) objects as `.summary` and `.summaries`.
- [`Batch`](../object-types/batch.md) objects after `processData`.
- Raw `pandas.DataFrame` input wrapped by [`from_dataframe`](../functions/from_dataframe.md) or passed directly to many plotting and pipeline functions.
- CSV and Excel exports written by object export methods.
- Pipeline result dictionaries and saved pipeline tables.

## Required Fields

For normal analysis, a usable summary table needs:

| Field | Meaning |
|---|---|
| `AnimalName` | Internal subject/sample identifier. DataFrame inputs can map another column to it with `subject_col`; `animal_col` remains a legacy alias. |
| `Condition` | Internal group label. DataFrame inputs can map another column to it with `group_col`; `condition_col` remains a legacy alias. |
| Metric columns | One or more numeric columns to plot, test, export, or model. |

Some low-level helpers can operate without `Condition`, but grouped plots,
condition-aware pipelines, and exports expect it.

## Optional Fields

Common optional columns include:

| Field or Pattern | Meaning |
|---|---|
| Factor columns such as `Diagnosis`, `Sex`, `Time` | Added from the group list and used by `factor`, `split_by`, `group_cols`, or `filter_by`. |
| `Region`, `ROI`, `ImageROI`, `ROINameRaw`, `Hemisphere` | ROI metadata carried from marker or ROI tables when available. |
| `numSections` | Number of ROI regions/sections contributing to a subject summary. |
| `ROI_Area`, `ROI_Volume`, `ROI_Thickness`, `Volume0p1mm3`, `CountNormFactor` | ROI normalization fields derived from ROI property tables or fallback configuration. |
| `<marker>_Count`, `<marker>_CountRaw` | Normalized and raw object counts. |
| `<marker>_IntDenTotal`, `<marker>_VolumeTotal`, `<marker>_SurfaceTotal` | Per-subject summed object measurements, volume-normalized where appropriate. |
| `<marker>_IntDenMean`, `<marker>_VolumeMean`, `<marker>_SurfaceMean`, `<marker>_SAtoVolumeRatioMean` | Per-subject means from row-level marker measurements. |
| `<marker>_ROI_IntDenMean`, `<marker>_ROI_%AreaMean` | ROI intensity summary columns from ROI intensity tables. |
| `<marker>_VolColoc_<other>_Count`, `<marker>_CPCColoc_<other>_Count`, and related `Mean`, `CountRaw`, `Count%` variants | Colocalisation and association summaries. The exact families depend on the imported marker tables. |
| `<marker>_burdenScore`, `<marker>_fragmentationScore` | Derived marker scores added when their source columns are available. |

Metric columns are intentionally open-ended. PyFLASH detects and formats many
marker-derived names by pattern rather than by a fixed closed list.

## Example

```text
| AnimalName | Condition | Diagnosis | Region | GFAP_VolumeTotal | GFAP_Count | ROI_Volume |
|---|---|---|---|---:|---:|---:|
| Mouse_01 | Control | Control | SCN1 | 123.4 | 42 | 1300000 |
| Mouse_02 | AD | AD | SCN1 | 156.7 | 51 | 1280000 |
```

For already-tabular data:

```python
import pandas as pd
from PyFLASH import from_dataframe

summary = pd.DataFrame({
    "Subject ID": ["Mouse_01", "Mouse_02"],
    "Diagnosis": ["Control", "AD"],
    "GFAP Volume": [123.4, 156.7],
})

exp = from_dataframe(
    summary,
    group_col="Diagnosis",
    subject_col="Subject ID",
)
```

## Produced By

- `Experiment.createSummary()` and `Experiment.processData()`.
- `MiniExperiment.createSummary()`.
- [`from_dataframe`](../functions/from_dataframe.md), which creates a `DataFrameExperiment`.
- `Batch.processData()`, which merges experiment summaries into `Batch.summaries`.
- Exclusion helpers such as [`exclude_animals`](../functions/exclusions.md), which return cleaned shallow copies.

## Consumed By

- Summary plot functions such as [`plot_mean_bars`](../functions/plot_mean_bars.md), [`plot_matrices`](../functions/plot_matrices.md), [`plot_regressions`](../functions/plot_regressions.md), and model summary plots.
- Pipeline functions such as [`correlation`](../functions/correlation.md), [`adjusted_correlation`](../functions/adjusted_correlation.md), [`data_overview`](../functions/data_overview.md), [`group_comparison`](../functions/group_comparison.md), [`linear_model`](../functions/linear_model.md), and [`rhythm`](../functions/rhythm.md).
- Export methods documented in [Excel workbooks](../outputs/excel-workbooks.md).
- [`format_summary_for_display`](../functions/format_summary_for_display.md), which returns a display-only copy with readable labels.

## Notes

- `Batch.summary` returns the `"SCN"` summary when present, otherwise the first summary table in `Batch.summaries`.
- When merging experiments into a batch, subjects absent from a particular experiment receive the `NOT_INCLUDED_IN_EXPERIMENT` sentinel in that experiment's metric columns.
- Manual and outlier exclusions write `EXCLUDED_...` sentinel strings into cleaned copies unless you explicitly request a different fill value. Numeric analysis treats these sentinels as missing.
- Duplicate metric names from multiple experiments can be disambiguated with `.expN` suffixes, such as `GFAP_Count.exp2`.
- Do not rely on display labels from Excel exports as programmatic column names. Use the internal summary column names in Python code.

## See Also

- [Batch](../object-types/batch.md)
- [Experiment](../object-types/experiment.md)
- [DataFrameExperiment](../object-types/dataframe-experiment.md)
- [Column selection](../parameters/column-selection.md)
- [ROI parameters](../parameters/roi.md)
