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

| Parameter | Meaning |
|---|---|
| `experiment` | Main data source for most plots and pipelines. Usually a `Batch`, `Experiment`, `MiniExperiment`, `DataFrameExperiment`, or another object exposing the attributes the function needs. |
| `batch` | Batch-like data source used by several statistical and modelling helpers, even when a `DataFrameExperiment` also works. |
| `source` | Function-specific source object, often an experiment/batch or a marker-level `DataFrame`. Check the function page because `source` is not one universal type. |
| `batch_or_df` | Batch-like object or raw `pandas.DataFrame` accepted by `iterative_model_sweep`. |
| Raw `DataFrame` first argument | Subject-level summary table used when the function calls PyFLASH's DataFrame adapter. Supply group and subject metadata when the table is not already named `Condition` and `AnimalName`. |

### `experiment` options

| Option | Behavior |
|---|---|
| `Batch` | Main processed PyFLASH object. Most plots and pipelines read `.summary`; ROI-aware calls may read `.summaries`. |
| `Experiment` | Single-experiment PyFLASH object with summary data and output paths. |
| `MiniExperiment` | Lightweight experiment-like object for flat CSV-style data. |
| `DataFrameExperiment` | Adapter-created wrapper around a raw summary table. |
| Raw `pandas.DataFrame` | Accepted only by functions that call the adapter. Image/location calls usually need richer object attributes such as `.data`, `.images`, or region dictionaries. |

For raw DataFrame input, the important aliases are:

| Preferred name | Meaning | Aliases |
|---|---|---|
| `group_col` | Column containing group labels such as `Control` or `AD`. | `condition_col`. |
| `group_cols` | Columns that define crossed groups, such as `["Diagnosis", "Sex"]`. | `factor_cols`. |
| `subject_col` | Column containing subject, animal, or sample identifiers. | `animal_col`. |
| `groups` | Group list that defines order, colors, and comparisons. | `group_list`, legacy `conditions`. |

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
