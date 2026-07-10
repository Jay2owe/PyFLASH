# Saving And Run Labels

## Summary

Saving parameters control whether PyFLASH writes files, where those files go,
and how repeated pipeline runs are handled. Plot functions usually write figures
under an object's figure path. Pipelines write a named run folder with figures,
tables, and a manifest.

## Used By

- Most plot functions through `save`.
- Figure helpers such as [`plot_condition_key`](../functions/plot_condition_key.md),
  [`plot_marker_pca`](../functions/plot_marker_pca.md),
  [`plot_power_curve`](../functions/plot_power_curve.md),
  [`plot_cosinor`](../functions/plot_cosinor.md), and
  [`plot_acrophase_clock`](../functions/plot_acrophase_clock.md), which also
  accept `save_path`, `save_name`, or `dpi`.
- Pipelines such as [`correlation`](../functions/correlation.md),
  [`adjusted_correlation`](../functions/adjusted_correlation.md),
  [`data_overview`](../functions/data_overview.md),
  [`group_comparison`](../functions/group_comparison.md),
  [`linear_model`](../functions/linear_model.md), and
  [`rhythm`](../functions/rhythm.md).
- Modelling helpers such as [`iterative_model_sweep`](../functions/iterative_model_sweep.md)
  and [`run_linear_model_pipeline`](../functions/run_linear_model_pipeline.md).
- Exclusion helpers that can save exclusion ledgers.

## Accepted Values

| Parameter | Accepted values | Behavior |
|---|---|---|
| `save` | `True` or `False`. | Enables or suppresses file writes. Functions may still return figures, tables, or manifests when `save=False`. |
| `save_path` | Folder path string or path-like object. | Overrides the destination folder for functions that support direct figure saving. |
| `save_name` | Filename stem. | Overrides the generated figure/table name where supported. |
| `output_dir` | Folder path. | Used by modelling helpers and some legacy workflows to place generated tables and figures. |
| `run_label` | Folder-safe label string or `None`. | Names a pipeline or modelling run folder. `None` lets supported pipelines derive a deterministic label from settings. |
| `if_exists` | `"overwrite"`, `"version"`, `"error"`, or `"skip"` for analysis pipelines. | Controls collisions with existing pipeline run folders. Legacy linear-model table output supports `"overwrite"`, `"version"`, and `"error"`. |
| `write_manifest` | `True` or `False`. | Pipeline option controlling `manifest.json` and run-index writes. |
| `dpi` | Integer. | Controls raster resolution or figure creation in functions that expose it. Shared SVG saving keeps text editable and saves with PyFLASH's figure-save settings. |
| `resume` | `True` or `False`. | `iterative_model_sweep` can resume a matching partial checkpoint when `save=True`. |

## Examples

Preview without writing files:

```python
from PyFLASH.plotting import plot_mean_bars

figures = plot_mean_bars(batch, data_cols=["GFAP_Count"], save=False)
```

Run a pipeline into a stable folder:

```python
from PyFLASH import correlation

result = correlation(
    batch,
    data_cols=["GFAP_Count", "Iba1_Count"],
    run_label="gfap_iba1_screen",
    if_exists="version",
)
```

Write a model sweep to a chosen directory:

```python
from PyFLASH import iterative_model_sweep

result = iterative_model_sweep(
    batch,
    target="Diagnosis",
    data_cols=["GFAP_Count", "Iba1_Count"],
    output_dir="outputs/model_sweep",
    resume=True,
)
```

## Interactions

Standalone plots usually call the shared figure saver, which writes SVG files
and keeps SVG text editable. Some functions also save CSV statistics or PNG
normality plots next to the figure.

Pipelines co-locate figures, CSV tables, `manifest.json`, and `_runs_index.csv`
under:

```text
Python Figures/<Pipeline Name>/<run_label>/
```

The shared pipeline `if_exists` policies are:

| Policy | Behavior |
|---|---|
| `"overwrite"` | Clear the existing generated run folder, then recompute. |
| `"version"` | Keep the old run and write to the next free suffix such as `_v2`. |
| `"error"` | Raise if the run folder already exists. |
| `"skip"` | Reuse the cached manifest when available instead of recomputing. |

Pipeline filter queues use one shared run folder for all queue items.
Files inside the folder are tagged by filter value so the queue produces one
combined manifest and one combined montage.

`save=False` is not the same as `if_exists="skip"`. `save=False` suppresses
writes for the current call. `if_exists="skip"` is a saved-run collision policy.

## Common Errors

- Expecting `save_path` to work on a pipeline that uses `run_label` and
  pipeline run folders instead.
- Passing `if_exists="skip"` to legacy linear-model table output, which only
  accepts `"overwrite"`, `"version"`, or `"error"`.
- Reusing a `run_label` with `if_exists="overwrite"` and expecting old files to
  remain.
- Assuming `save=False` means no computation happens. Most functions still
  compute and return results.
- Choosing a `run_label` that sanitizes to an empty folder name.

## See Also

- [Figure folders](../outputs/figure-folders.md)
- [Pipeline run folders](../outputs/pipeline-run-folders.md)
- [Model sweep outputs](../outputs/model-sweep-outputs.md)
- [Normality outputs](../outputs/normality-outputs.md)
