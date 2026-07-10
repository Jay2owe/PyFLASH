# DataFrameExperiment

## Summary

`DataFrameExperiment` is a PyFLASH-compatible object backed by user-supplied
`pandas.DataFrame` objects. It is the object returned by
[`from_dataframe`](../functions/from_dataframe.md), and it is also used
internally when a plot or pipeline accepts a raw DataFrame directly.

Use it when your data is already tabular and you do not need to import a
FLASH/ImageJ folder.

## How To Create It

Preferred helper:

```python
import pandas as pd
from PyFLASH import from_dataframe

df = pd.DataFrame({
    "Subject": ["C1", "C2", "A1", "A2"],
    "Diagnosis": ["Control", "Control", "AD", "AD"],
    "Marker A": [1.0, 1.2, 2.0, 2.2],
})

experiment = from_dataframe(
    df,
    group_col="Diagnosis",
    subject_col="Subject",
    group_order=["Control", "AD"],
    group_comparisons=[("Control", "AD")],
    fig_path="/path/to/figures",
    data_path="/path/to/data",
)
```

You can also pass a pre-built group list:

```python
from PyFLASH import GroupBuilder, from_dataframe

groups = (
    GroupBuilder("Diagnosis")
    .add("Control", short="Control", color="grey")
    .add("AD", short="AD", color="red")
    .compare("Control", "AD")
    .build()
)

experiment = from_dataframe(
    df,
    group_list=groups,
    group_col="Diagnosis",
    subject_col="Subject",
)
```

Several plots and pipelines accept raw DataFrames directly with the same column
aliases:

```python
from PyFLASH.plotting import plot_mean_bars

plot_mean_bars(
    df,
    data_cols=["Marker A"],
    group_col="Diagnosis",
    subject_col="Subject",
    save=False,
)
```

## Important Attributes

| Attribute | Meaning |
|---|---|
| `data_layout` | Always `"dataframe"`. |
| `name` | Object name, defaulting to `"DataFrame"`. |
| `condition_list` | Condition or group list, either supplied by the user or inferred from grouping columns. |
| `factor` | List of factor column names. |
| `factorDict` | Mapping from factor names to group objects. |
| `aliases` | Optional alias dictionary supplied to the constructor. |
| `filePath` | Base path used for default output folders. Defaults to the current working directory when `file_path` is not supplied. |
| `fig_path` | Base folder for saved figures. |
| `data_path` | Base folder for saved statistics and data outputs. |
| `export_path` | Base folder for exports. |
| `image_fig_path`, `representative_path`, `legend_path` | Standard figure-related output folders. |
| `summary` | Normalized subject-level summary table. It includes internal `AnimalName` and `Condition` columns. |
| `summaries` | Dictionary of summary tables keyed by region of interest base. Defaults to `{roi_base: summary}`. |
| `region_dicts` | Condition to subject to region mappings for each summary table. |
| `region_dict` | Primary region mapping for the selected `roi_base`. |
| `data` | Optional marker-level tables supplied through `data=...`, wrapped so each value has `.df`. |
| `markers` | Set of keys in `data`. |
| `images` | Optional image metadata DataFrame or value supplied by the user. |
| `imagesDict` | Empty dictionary by default. |
| `representative_images` | Optional representative-image metadata supplied by the user. |

## Common Methods

| Method | Use |
|---|---|
| `createSavePaths()` | Create standard output folders and return `self`. |
| `getRegionDict(roi_base=None)` | Return the condition to subject to region mapping used by iteration. |
| `set_condition_list(condition_list)` | Replace the group list and update `factor` and `factorDict`. |
| `processData(*_, **__)` | Compatibility no-op. A `DataFrameExperiment` is already processed at construction time. |

## Accepted By

`DataFrameExperiment` is accepted by summary-first plots, matrix plots,
regression plots, pipelines that operate on summary tables, exclusion helpers,
and formatting helpers. It can also provide marker-level tables to plots such
as histograms when `data=...` is supplied.

## Returned By

- [`from_dataframe`](../functions/from_dataframe.md)
- Internal DataFrame coercion used by plots and pipelines that accept a raw
  `pandas.DataFrame`
- [`load_state`](../functions/load_state.md), when a saved pickle contains a
  `DataFrameExperiment`

## Examples

Create groups automatically from one column:

```python
experiment = from_dataframe(
    df,
    group_col="Diagnosis",
    subject_col="Subject",
    group_colors={"Control": "grey", "AD": "red"},
)

print(experiment.summary[["AnimalName", "Condition"]])
```

Create crossed groups from factor columns:

```python
experiment = from_dataframe(
    df,
    group_cols=["Diagnosis", "Sex"],
    subject_col="Subject",
    fig_path="/path/to/figures",
)

print(experiment.condition_list.factor)
print(experiment.summary["Condition"].head())
```

Supply marker-level data for marker plots:

```python
cells = pd.DataFrame({
    "Subject": ["C1", "C1", "A1", "A1"],
    "Area": [10.0, 11.0, 20.0, 21.0],
})

experiment = from_dataframe(
    df,
    group_col="Diagnosis",
    subject_col="Subject",
    data={"Cells": cells},
)

print(experiment.data["Cells"].df.head())
```

## Notes

- `group_col`, `group_cols`, and `subject_col` are user-facing aliases for
  `condition_col`, `factor_cols`, and `animal_col`.
- Internally, PyFLASH normalizes subject and group columns to `AnimalName` and
  `Condition`.
- `DataFrameExperiment` does not import ImageJ marker folders, ROI ZIP files, or
  image folders. Provide marker-level tables and image metadata explicitly if a
  workflow needs them.
- When no conditions are supplied, conditions can be inferred from `group_col`,
  `group_cols`, `condition_col`, or `factor_cols`.

## See Also

- [`from_dataframe`](../functions/from_dataframe.md)
- [Input object parameters](../parameters/input-objects.md)
- [Column selection parameters](../parameters/column-selection.md)
- [Load table gallery example](../gallery/load-table-with-from-dataframe.md)
- [Data structures: summary table](../data-structures/summary-table.md)
