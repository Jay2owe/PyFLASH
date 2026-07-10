# Object Model

PyFLASH functions work with a small set of Python objects. The usual workflow
is:

1. Build a group list.
2. Create or load a `Batch`.
3. Inspect `batch.summary`.
4. Pass the object to plots, pipelines, exports, or modelling functions.

Most users only need `Batch`, `DataFrameExperiment`, and group objects.
`Experiment`, `MiniExperiment`, and marker objects are useful when you need to
understand how data was imported.

| Object | Detailed Page | Role |
|---|---|---|
| `Batch` | [Batch](object-types/batch.md) | A processed collection of one or more experiments with shared conditions. |
| `Experiment` | [Experiment](object-types/experiment.md) | One imported FLASH/ImageJ experiment folder. |
| `MiniExperiment` | [MiniExperiment](object-types/mini-experiment.md) | A lightweight experiment for a folder of flat CSV tables. |
| `DataFrameExperiment` | [DataFrameExperiment](object-types/dataframe-experiment.md) | A PyFLASH-compatible wrapper around user-supplied `pandas.DataFrame` tables. |
| `group`, `groupList`, `GroupBuilder` | [Groups](object-types/conditions.md) | Group labels, colors, factors, styles, and planned comparisons. |
| `condition`, `conditionList`, `ConditionBuilder` | [Groups](object-types/conditions.md) | Legacy aliases for the group objects. |
| `Attribute`, `Antibody`, `cellMarker`, `objectMarker` | [Markers](object-types/markers.md) | Imported marker and attribute tables inside `experiment.data` or `batch.data`. |
| `Config` | [Config](object-types/config.md) | Package-wide defaults for thresholds, colors, saving, aliases, and figure behavior. |

## Main Relationships

`Batch` contains an ordered `experiment_list`. Each item is usually an
`Experiment` created from a FLASH/ImageJ output folder, but it can also be a
`MiniExperiment` when the input is a folder of ordinary CSV files.

`Experiment`, `MiniExperiment`, and `DataFrameExperiment` expose a compatible
surface: `summary`, `summaries`, `data`, `condition_list`, `factor`, `factorDict`,
and output paths such as `fig_path`. This is why many plotting and pipeline
functions can accept any of those objects.

Group objects describe the groups in the experiment. They do not hold
measurements. They tell PyFLASH how to label rows, order groups, color plots,
style crossed factors, and resolve planned comparisons.

Marker objects wrap measurement tables. Most users inspect them through
`batch.data["MarkerName"].df` instead of constructing marker objects directly.

## Internal Compatibility Columns

Public table APIs use `group_col` and `subject_col` aliases where possible.
Internally PyFLASH still normalizes these to `Condition` and `AnimalName` so
older image, export, and pickle workflows remain compatible.

## See Also

- [Object type reference](object-types/README.md)
- [Input object parameters](parameters/input-objects.md)
- [Create a batch workflow](workflows/create-a-batch.md)
- [Load a table with `from_dataframe`](gallery/load-table-with-from-dataframe.md)
