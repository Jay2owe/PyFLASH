# Object Types

This section documents the Python objects users create, inspect, and pass into
PyFLASH functions. Start with `Batch` for folder-backed analysis, or
`DataFrameExperiment` for already-tabular data.

| Page | Use It For |
|---|---|
| [Batch](batch.md) | A processed collection of experiments, summary tables, conditions, paths, images, and export methods. |
| [Experiment](experiment.md) | One full FLASH/ImageJ experiment folder and its imported marker tables. |
| [MiniExperiment](mini-experiment.md) | A folder of simple CSV tables that should behave like an experiment. |
| [DataFrameExperiment](dataframe-experiment.md) | In-memory `pandas.DataFrame` input for plots and pipelines. |
| [Groups](conditions.md) | `group`, `groupList`, crossed designs, colors, styles, and comparisons. Classic `condition` names remain supported. |
| [Markers](markers.md) | `Attribute`, `Antibody`, `cellMarker`, and `objectMarker` objects inside `.data`. |
| [Config](config.md) | Global defaults such as thresholds, colors, saving behavior, montage filenames, and aliases. |

## Choosing An Input Object

| Starting Point | Recommended Object |
|---|---|
| FLASH/ImageJ output folders | Use [`create_batch`](../functions/create_batch.md), which returns a [`Batch`](batch.md). |
| One folder of flat CSV files | Create a [`MiniExperiment`](mini-experiment.md), then place it in a [`Batch`](batch.md). |
| A `pandas.DataFrame` summary table | Use [`from_dataframe`](../functions/from_dataframe.md), which returns a [`DataFrameExperiment`](dataframe-experiment.md). |
| A raw table passed directly to a plot or pipeline | Use `group_col` and `subject_col`; PyFLASH wraps it internally as a [`DataFrameExperiment`](dataframe-experiment.md). |
| Existing processed pickle | Use [`load_state`](../functions/load_state.md), which returns the object that was saved. |

## Stable Vocabulary

- A **subject** or **animal** is stored in the `AnimalName` column inside
  PyFLASH objects.
- A **group** or **condition** is stored in the `Condition` column.
- `group`, `groupList`, and `GroupBuilder` are aliases for the older
  `condition`, `conditionList`, and `ConditionBuilder` names.
- A **summary table** is subject-level data in `.summary` or `.summaries`.
- A **marker table** is row-level measurement data in `.data["name"].df`.

See also: [Object model](../object-model.md).
