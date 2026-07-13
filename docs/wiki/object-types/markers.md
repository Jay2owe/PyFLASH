# Marker Objects

## Summary

Marker objects wrap imported measurement tables. They are the values stored in
`experiment.data` and `batch.data`, and each one exposes its table as `.df`.

Most users inspect marker objects rather than constructing them directly. The
full import pipeline chooses the object type from the source folder:

| Object | Typical Source | Role |
|---|---|---|
| `Attribute` | ROI properties, behavior, generic tables, flat CSVs | Generic table wrapper with cleaned columns and condition metadata. |
| `Antibody` | ROI intensity tables | Marker intensity table with marker-prefixed columns. |
| `cellMarker` | Cell marker object tables | Object table without colocalisation summary generation. |
| `objectMarker` | Object marker tables | Object table with colocalisation count and closest-distance support. |

## How To Create It

Usually through [`Experiment`](experiment.md) or [`Batch`](batch.md) processing:

```python
from PyFLASH import create_batch

batch = create_batch(
    "example",
    groups,
    "/path/to/output-folder",
    experiments="/path/to/experiment-parent-folder",
    import_images=False,
)

marker = batch.data["GFAP"]
print(type(marker).__name__)
print(marker.df.head())
```

Direct construction is mainly for advanced code and tests:

```python
from PyFLASH import Attribute

attribute = Attribute("Behavior", behavior_df, experiment)
```

`Antibody`, `cellMarker`, and `objectMarker` constructors also take an
experiment object and a color. The color is optional for `Antibody`
(`color=None`) but required for `cellMarker` and `objectMarker`. `objectMarker`
can take a `threshold` argument.

## Important Attributes

| Attribute | Applies To | Meaning |
|---|---|---|
| `name` | All marker objects | Marker or table name used as the key in `.data`. |
| `df` | All marker objects | Cleaned `pandas.DataFrame` containing the imported measurements. |
| `experiment` | All marker objects | Parent experiment. This is removed during pickling and re-linked after loading. |
| `color` | `Antibody`, `cellMarker`, `objectMarker` | Marker color used by plotting helpers. |
| `threshold` | `objectMarker` | Stored constructor value. Current automatic cleaning calls `addColocData(Config.THRESHOLD)`; call `addColocData(threshold)` explicitly if you need a different threshold. |

Important table columns vary by source file. Common normalized columns include
`AnimalName`, `Condition`, `Region`, `ROI`, and marker-prefixed measurement
columns such as `GFAP_Count` or `GFAP_IntDen`.

## Common Methods

| Method | Applies To | Use |
|---|---|---|
| `set_df(new_df)` | `Antibody` and subclasses | Replace the stored DataFrame and return it. |
| `addColocData(threshold)` | `objectMarker` through `Antibody` implementation | Add colocalisation count columns from raw colocalisation fields. |
| `analyse_roi(roi, points, visualise=False)` | `Antibody` and subclasses | Compute distances from points to an ROI line; optionally save a diagnostic figure. |
| `find_distance_to_ventricle(rois)` | `cellMarker`, `objectMarker` | Add distance-to-ventricle values when ROI data is available. |
| `find_closest_distances_between_markers(other_marker)` | `cellMarker`, `objectMarker` | Add nearest-neighbor distance and closest-marker columns between markers. |

Most lower-level cleaning methods are implementation details. Prefer reading
or filtering `.df` unless you are extending PyFLASH.

## Accepted By

Marker objects are not usually passed directly to public plotting functions.
Instead, pass the parent `Batch`, `Experiment`, or `DataFrameExperiment` and
refer to marker tables by name:

```python
from PyFLASH.plotting import plot_histograms

plot_histograms(
    batch,
    marker="GFAP",
    x_attr="GFAP_Area",
    save=False,
)
```

Internally, marker-aware plots and pipelines look up marker tables in
`obj.data`.

## Returned By

Marker objects are created by:

- `Experiment.importCSVs()`
- `Experiment.processData()`
- `MiniExperiment.importCSVs()` for flat CSV `Attribute` tables
- `Batch.processData()`, which merges experiment `.data` dictionaries into
  `batch.data`
- [`load_state`](../functions/load_state.md), when loading a saved object that
  contains marker tables

## Examples

List marker tables:

```python
print(sorted(batch.data))

for name, table in batch.data.items():
    print(name, type(table).__name__, table.df.shape)
```

Inspect one table:

```python
gfap = batch.data["GFAP"].df
print(gfap.columns.tolist())
print(gfap[["AnimalName", "Condition"]].head())
```

Filter marker rows before custom analysis:

```python
gfap = batch.data["GFAP"].df
control = gfap.loc[gfap["Condition"] == "Control"].copy()
```

Use table data from a `DataFrameExperiment`:

```python
from PyFLASH import from_dataframe

experiment = from_dataframe(
    summary_df,
    group_col="Diagnosis",
    subject_col="Subject",
    data={"Cells": cell_df},
)

print(experiment.data["Cells"].df.head())
```

## Notes

- `Attribute` cleans column names and ensures a `Condition` column based on
  animal names or condition labels.
- `Antibody` prefixes measurement columns with the marker name.
- `cellMarker` and `objectMarker` adjust coordinate columns when ROI properties
  are available.
- `objectMarker` adds colocalisation count-style columns from raw
  colocalisation measurements.
- Source CSV headers are normalized. If a raw column seems missing, inspect
  `marker.df.columns`.

## See Also

- [Experiment](experiment.md)
- [Batch](batch.md)
- [DataFrameExperiment](dataframe-experiment.md)
- [Marker tables](../data-structures/marker-tables.md)
- [Image panels](../plot-types/image-panels.md)
- [Location plots](../plot-types/location-plots.md)
- [Colocalisation plots](../plot-types/colocalisation-plots.md)
