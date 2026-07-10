# Input Objects

## Summary

Input-object parameters say where PyFLASH should read data from. The common
case is a PyFLASH object with a subject-level `.summary` table. Some functions
also accept a raw `pandas.DataFrame` and wrap it as a
[`DataFrameExperiment`](../object-types/dataframe-experiment.md) before running.

## Used By

- Summary plots such as [`plot_mean_bars`](../functions/plot_mean_bars.md),
  [`plot_matrices`](../functions/plot_matrices.md),
  [`plot_regressions`](../functions/plot_regressions.md),
  [`plot_radar`](../functions/plot_radar.md), and group-summary plots.
- Pipelines such as [`correlation`](../functions/correlation.md),
  [`adjusted_correlation`](../functions/adjusted_correlation.md),
  [`data_overview`](../functions/data_overview.md),
  [`group_comparison`](../functions/group_comparison.md),
  [`linear_model`](../functions/linear_model.md), and
  [`rhythm`](../functions/rhythm.md).
- Modelling helpers such as
  [`iterative_best_fit`](../functions/iterative_best_fit.md) and
  [`iterative_model_sweep`](../functions/iterative_model_sweep.md).
- Image, location, and colocalisation plots that need marker tables or images.
- Exclusion helpers such as [`exclusions`](../functions/exclusions.md), which
  expect an experiment-like object rather than a bare summary table.

## Accepted Values

| Parameter | Accepted values | Notes |
|---|---|---|
| `experiment` | `Batch`, `Experiment`, `MiniExperiment`, `DataFrameExperiment`, or another object exposing the attributes the function needs. | Most plots and pipelines read `.summary`; ROI-aware calls may read `.summaries`; image/location calls may also read `.data`, `.images`, or region dictionaries. |
| `batch` | Usually a `Batch` or batch-like object with `.summary` and output paths. | Several statistical and modelling helpers use this name even when a `DataFrameExperiment` also works. |
| `source` | Function-specific source object, often an experiment/batch or a marker-level `DataFrame`. | Used by colocalisation and image-related functions. Check the function page because `source` is not one universal type. |
| `batch_or_df` | A batch-like object or a raw `pandas.DataFrame`. | Used by `iterative_model_sweep`. |
| Raw `DataFrame` first argument | A subject-level summary table, when the function calls PyFLASH's DataFrame adapter. | Supply `group_col`/`subject_col`, or `conditions`/`groups` plus factor columns when the table is not already named `Condition` and `AnimalName`. |

For raw DataFrame input, the important aliases are:

| Public alias | Internal name | Meaning |
|---|---|---|
| `group_col` | `condition_col` | Column containing group labels such as `Control` or `AD`. |
| `group_cols` | `factor_cols` | Columns that define crossed groups, such as `["Diagnosis", "Sex"]`. |
| `subject_col` | `animal_col` | Column containing subject or animal identifiers. |
| `groups` / `group_list` | `conditions` | A group list that defines order, colors, and comparisons. |

## Examples

Use an existing PyFLASH object:

```python
from PyFLASH.plotting import plot_matrices

plot_matrices(batch, data_cols=["GFAP_Count", "Iba1_Count"], save=False)
```

Use a plain table:

```python
from PyFLASH.plotting import plot_mean_bars

plot_mean_bars(
    df,
    data_cols=["GFAP_VolumeTotal"],
    group_col="Diagnosis",
    subject_col="Mouse ID",
    save=False,
)
```

Use crossed group columns from a table:

```python
from PyFLASH import data_overview

result = data_overview(
    df,
    data_cols=["GFAP_Count", "Iba1_Count"],
    group_cols=["Diagnosis", "Sex"],
    subject_col="AnimalName",
    split_by=["Condition", "Sex"],
    save=False,
)
```

## Interactions

Raw DataFrame support depends on the function. DataFrame-aware plots and
pipelines call the adapter and create a `.summary`, `.summaries`, condition
list, and default output paths. Lower-level helpers that never call the adapter
need a PyFLASH-like object directly.

`group_col` creates or maps the canonical `Condition` column. It is different
from [`split_by`](conditions-and-factors.md), which chooses how an already
prepared table is panelled or grouped for analysis.

If `group_cols`/`factor_cols` are supplied, PyFLASH can build crossed groups
from multiple columns and derive `Condition` from the component levels.

## Common Errors

- Passing a raw DataFrame to a helper that expects an object with `.summary`,
  `.summaries`, `.data`, or output paths.
- Using `split_by="Diagnosis"` without also telling the DataFrame adapter which
  column defines the primary group, usually `group_col="Diagnosis"`.
- Supplying a table without any usable subject column. If `subject_col` or
  `AnimalName` is missing, the adapter falls back to the DataFrame index.
- Supplying only a subject-level summary table to an image, location, or
  marker-level plot that needs raw marker tables or image metadata.

## See Also

- [Summary table](../data-structures/summary-table.md)
- [Batch](../object-types/batch.md)
- [DataFrameExperiment](../object-types/dataframe-experiment.md)
- [Groups](../object-types/conditions.md)
- [`from_dataframe`](../functions/from_dataframe.md)
