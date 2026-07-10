# from_dataframe

## Summary

`from_dataframe` wraps already-tabular data in a PyFLASH-compatible object. It
lets users provide their own summary table, optional groups, output paths,
optional ROI-specific summaries, and optional marker-level tables.

Use it when the data is already clean and you want to run several PyFLASH
functions without importing a FLASH/ImageJ folder. For one-off plots and
pipelines, several functions can now accept a raw DataFrame directly with
`group_col=...`, `group_cols=...`, and `subject_col=...`.

## Signature

```python
from_dataframe(
    summary,
    group_list=None,
    *,
    name="DataFrame",
    group_col=None,
    group_cols=None,
    subject_col=None,
    factor_mappings=None,
    fig_path=None,
    data_path=None,
    file_path=None,
    aliases=None,
    summaries=None,
    data=None,
    images=None,
    representative_images=None,
    roi_base="SCN",
    region_col=None,
)
```

## Input Object Types

| Object type | Accepted? | Notes |
|---|---:|---|
| `pandas.DataFrame` | Yes | Required as `summary`. Optional marker tables in `data` must also be DataFrames or objects with `.df`. |
| `groupList` / `conditionList` | Yes | Optional as `group_list`. Build it with `GroupBuilder`/`ConditionBuilder` or the classic condition API. |
| `Batch` | No | Use `Batch` directly; no wrapping needed. |
| `Experiment` | No | Use `Experiment` directly; no wrapping needed. |

## Parameters

| Parameter | Type | Default | Meaning |
|---|---|---:|---|
| `summary` | `pandas.DataFrame` | required | Summary-level table, usually one row per animal or subject. |
| `group_list` | `groupList` or `None` | `None` | Optional group metadata. If omitted, PyFLASH infers defaults from `group_col` or `group_cols`. |
| `name` | `str` | `"DataFrame"` | Name stored on the returned object. |
| `group_col` | `str` or `None` | `None` | Column whose values identify the PyFLASH group. When omitted, PyFLASH falls back to a `Condition` column (via the legacy `condition_col="Condition"` default) or derives it from `group_cols`. |
| `group_cols` | list-like or `None` | `None` | One or more grouping columns used to infer simple or crossed groups. |
| `subject_col` | `str` or `None` | `None` | Column containing subject, sample, or animal IDs. When omitted, PyFLASH falls back to an `AnimalName` column (via the legacy `animal_col="AnimalName"` default), then to the row index. |
| `factor_mappings` | `dict` or `None` | `None` | Optional value remapping for factor columns, e.g. `"Healthy control"` to `"Control"`. |
| `group_order` | list-like, dict, or `None` | `None` | Optional order for inferred group or factor levels. Legacy alias: `condition_order`. |
| `group_labels` | list-like, dict, or `None` | `None` | Optional display labels for inferred groups. |
| `group_colors` | list-like, dict, or `None` | `None` | Optional colors for inferred groups. |
| `group_styles` | list-like, dict, or `None` | `None` | Optional bar styles for inferred groups. |
| `group_comparisons` | list-like or `None` | `None` | Optional default group comparisons. Legacy alias: `comparisons`. |
| `group_comparison_mode` | `str` or `None` | `None` | Optional inferred comparisons: `"all"`, `"control"`, or `"sequential"`. Legacy alias: `comparison_mode`. |
| `group_control` | `str` or `None` | `None` | Control group name used when `group_comparison_mode="control"`. Legacy alias: `control`. |
| `fig_path` | Path-like or `None` | `None` | Folder used by plotting functions when `save=True`. |
| `data_path` | Path-like or `None` | `None` | Folder used by pipeline functions for result tables. |
| `file_path` | Path-like or `None` | `None` | Base path used to derive default output folders. |
| `aliases` | `dict` or `None` | `None` | Optional filename/label aliases. |
| `summaries` | `dict[str, pandas.DataFrame]` or `None` | `None` | Optional ROI-specific summary tables. |
| `data` | `dict[str, pandas.DataFrame]` or `None` | `None` | Optional marker-level tables, available as `obj.data[name].df`. |
| `images` | `pandas.DataFrame` or `None` | `None` | Optional image metadata table for future image workflows. |
| `representative_images` | `pandas.DataFrame` or `None` | `None` | Optional representative-image selection table. |
| `roi_base` | `str` | `"SCN"` | Default key for `summaries`. |
| `region_col` | `str` or `None` | `None` | Optional region column used to build `getRegionDict()`. |

Legacy aliases still work: `conditions`, `condition_col`, `factor_cols`,
`animal_col`, and the older `condition_*` style options.

## Returns

| Return value | Type | Meaning |
|---|---|---|
| `obj` | `DataFrameExperiment` | PyFLASH-compatible object with `summary`, `condition_list`, `fig_path`, `data_path`, `summaries`, optional `data`, and `getRegionDict()`. |

## Supported Workflows

| Workflow | Status | Notes |
|---|---:|---|
| Summary plots | Supported | Examples: `plot_mean_bars`, `plot_matrices`, `plot_regressions`, `plot_volcano`, `plot_radar`. |
| Summary pipelines | Supported | Examples: `correlation`, `data_overview`, `group_comparison`, `linear_model` when required columns are present. |
| Modelling | Supported | Use the wrapped object, or pass a DataFrame directly to functions that explicitly support it. |
| Marker distribution plots | Partly supported | Pass marker tables through `data={"Marker": df}`. |
| Image/location plots | Advanced | Require image metadata, ROI geometry, and coordinate conventions. |
| Excel exports | Not the first target | Export code assumes more of the full Batch/Experiment import structure. |

## Examples

### Summary table with one grouping column

```python
import pandas as pd
from PyFLASH import GroupBuilder, from_dataframe
from PyFLASH.plotting import plot_mean_bars

df = pd.DataFrame({
    "Subject ID": ["C1", "C2", "A1", "A2"],
    "Diagnosis": ["Control", "Control", "AD", "AD"],
    "GFAP Volume": [1.0, 1.1, 2.0, 2.2],
})

groups = (
    GroupBuilder("Diagnosis")
    .add("Control", short="Control", color="grey")
    .add("AD", short="AD", color="red")
    .compare("Control", "AD")
    .build()
)

exp = from_dataframe(
    df,
    group_list=groups,
    group_col="Diagnosis",
    subject_col="Subject ID",
    fig_path="Results/Python Figures",
)

plot_mean_bars(exp, data_cols=["GFAP Volume"])
```

### Direct one-off plotting call

```python
from PyFLASH.plotting import plot_mean_bars

plot_mean_bars(
    df,
    data_cols=["GFAP Volume"],
    group_col="Diagnosis",
    subject_col="Subject ID",
    save=False,
)
```

This call internally wraps `df` with `from_dataframe`, then runs the normal
PyFLASH plotting code.

### Crossed design derived from factor columns

```python
diagnosis = (
    GroupBuilder("Diagnosis")
    .add("Control", short="Control", color="grey")
    .add("AD", short="AD", color="red")
    .build()
)
sex = (
    GroupBuilder("Sex")
    .add("Female", short="Female")
    .add("Male", short="Male")
    .build()
)
groups = GroupBuilder.cross(diagnosis, sex).build()

exp = from_dataframe(
    df,
    group_list=groups,
    group_cols=["Diagnosis", "Sex"],
    subject_col="Subject ID",
)
```

If `df` contains `Diagnosis` and `Sex`, PyFLASH derives the combined internal
group labels from those factor columns.

### Direct pipeline call with crossed factors

```python
from PyFLASH import correlation

result = correlation(
    df,
    data_cols=["GFAP Volume"],
    against_data_cols=["Iba1 Volume"],
    group_cols=["Diagnosis", "Sex"],
    subject_col="Subject ID",
    split_by="Diagnosis",
    save=False,
)
```

Here `group_cols` is used to infer the full crossed group design, while
`split_by="Diagnosis"` tells the correlation pipeline to report panels grouped
by diagnosis.

### Marker-level table for distribution plots

```python
cells = pd.DataFrame({
    "Subject ID": ["C1", "C1", "A1", "A1"],
    "Area": [10.0, 11.0, 20.0, 21.0],
})

exp = from_dataframe(
    df,
    group_list=groups,
    group_col="Diagnosis",
    subject_col="Subject ID",
    data={"Cells": cells},
)

from PyFLASH.plotting import plot_histograms

plot_histograms(exp, marker="Cells", x_attr="Area")
```

Marker tables are enriched from the summary table by the subject IDs, so they
do not need to repeat group labels if the IDs match.

## Notes

- `from_dataframe` does not import raw ImageJ files. It only adapts already
  tabular data.
- The returned object is already processed; `processData()` is a no-op for
  compatibility.
- If `group_list` is omitted, default group objects are inferred from
  `group_col` or `group_cols`.
- Values in `group_col` are mapped against group names and labels when
  explicit groups are provided.
- If `group_col` is absent, all factors in the supplied `groupList` must be
  present as columns so the internal group column can be derived.
- If `subject_col` is absent, the row index is used as the internal subject ID.

## See Also

- [Object model](../object-model.md)
- `create_batch`
- `GroupBuilder`
- `plot_mean_bars`
- `correlation`
