# plot_ridgeline

## Summary

`plot_ridgeline` draws stacked density curves for a marker-level attribute,
grouped by condition or factor. It is registered as `ridgeline` in
`PyFLASH.spec.PLOT_REGISTRY`.

Use it when you want to compare the shapes of several distributions in one
compact figure.

## Example figure

<!-- gallery-example-code:start -->
Gallery render call (after `ex = build_example_data(fig_path=TMP)`, `exp = ex.experiment`, and `P = PyFLASH.plotting`):

```python
P.plot_ridgeline(exp, marker="Marker1", x_attr="Volume", save=True)
```
<!-- gallery-example-code:end -->

![plot_ridgeline example figure](../gallery/images/plot_ridgeline.svg)

*`Marker1` volume density ridges per group. Rendered from the [synthetic example dataset](../examples/README.md).*

## Signature

```python
plot_ridgeline(
    experiment,
    marker,
    x_attr,
    by="conditions",
    factor=None,
    ridge_height=0.85,
    alpha=0.55,
    line_width=1.5,
    bw_adjust=1.0,
    save=True,
    specificity=None,
    filter_by=None,
    roi=None,
    bottom_ticks=True,
    bottom_tick_labels=True,
    x_range=None,
    xmin=None,
    xmax=None,
    share_axes=True,
)
```

## Input Object Types

| Object type | Accepted? | Notes |
|---|---:|---|
| `Batch` | Yes | Main supported input when marker tables were imported. |
| `Experiment` | Yes | Must expose `data[marker].df`, `condition_list`, `summary`, and `fig_path`. |
| `MiniExperiment` | Only if marker tables exist | A summary-only mini experiment is not enough. |
| `pandas.DataFrame` | No direct raw table mode | Wrap raw tables with `from_dataframe(..., data=...)` first so the marker table exists. |

## Parameters

| Parameter | Type | Default | Meaning |
|---|---|---:|---|
| `experiment` | `Batch` or `Experiment` | required | Data source containing marker tables. |
| `marker` | `str` or list-like | required | Marker table key. List-like values queue plots. |
| `x_attr` | `str` or list-like | required | Attribute to plot. May be a full marker-table column or marker suffix. List-like values queue plots. |
| `by` | `str` | `"conditions"` | Iteration level. |
| `factor` | `str` or `None` | `None` | Group by factor values instead of conditions. |
| `ridge_height` | number | `0.85` | Vertical height for each density ridge. Values are clamped to at least `0.05`. |
| `alpha` | number | `0.55` | Fill transparency, clamped between `0` and `1`. |
| `line_width` | number | `1.5` | Outline width for each density curve. |
| `bw_adjust` | number | `1.0` | Kernel-density bandwidth multiplier. Larger values smooth more. |
| `save` | `bool` | `True` | Save the SVG figure under the input object's figure folder. |
| `filter_by` | dict, tuple, queue, or `None` | `None` | Row filter applied before plotting. A queue returns a dictionary keyed by filter. Alias: `specificity`. |
| `roi` | `str`, list-like, or `None` | `None` | ROI-base selector. Multiple ROI bases run queue mode. |
| `bottom_ticks` | `bool` | `True` | Show bottom-axis tick marks. |
| `bottom_tick_labels` | `bool` | `True` | Show bottom-axis tick labels. |
| `x_range` | `(min, max)` or `None` | `None` | Explicit x-axis range. |
| `xmin`, `xmax` | number or `None` | `None` | Convenience aliases for lower/upper values in `x_range`. |
| `share_axes` | `bool` | `True` | Use registered axis limits when available and no explicit range is supplied. |

## Parameter Options

### `by` options

| Option | Behavior |
|---|---|
| `"conditions"` (default) | Iterate over resolved conditions/groups. |

## Returns

| Return value | Type | Meaning |
|---|---|---|
| result | `dict` | Shared runner output. Keys commonly include `group` and `n` lists. |
| queued result | `dict` | When `marker`, `x_attr`, `filter_by`, or `roi` is queued, returns nested dictionaries keyed by the queued values. |

The return value records processed groups and row counts. It is not a persistent
figure handle.

## Saved Outputs

When `save=True`, one SVG figure is written below `experiment.fig_path` under
`<marker>/Ridgelines/`, for example `GFAP/Ridgelines`. Factor and row-filter
contexts are encoded into filename suffixes. When several ROI bases are queued,
the ROI base is prepended as a top-level folder.

Common filename:

```text
<x column> Ridgeline.svg
```

## Examples

### Plot one ridgeline figure

```python
from PyFLASH.plotting import plot_ridgeline

result = plot_ridgeline(
    batch,
    marker="GFAP",
    x_attr="Volume",
    save=False,
)

print(result.get("n"))
```

### Adjust smoothing and range

```python
plot_ridgeline(
    batch,
    marker="GFAP",
    x_attr="Volume",
    bw_adjust=0.7,
    x_range=(0, 500),
)
```

### Group by a factor

```python
plot_ridgeline(
    batch,
    marker="GFAP",
    x_attr="Volume",
    factor="Diagnosis",
    ridge_height=0.7,
)
```

### Inspect queued output

```python
queued = plot_ridgeline(
    batch,
    marker=["GFAP", "Iba1"],
    x_attr="Volume",
    save=False,
)

for key, value in queued.items():
    print(key, value.get("group"))
```

## Notes

- A ridgeline requires at least one finite numeric value after filtering.
- Increase `bw_adjust` for smoother curves and decrease it to reveal sharper
  local structure.
- `ridgeline` is describe-layer exempt: it is a descriptive distribution plot
  and does not emit structured inferential report records.

## See Also

- [Distribution plots](../plot-types/distribution-plots.md)
- [`plot_histograms`](plot_histograms.md)
- [`plot_ecdf`](plot_ecdf.md)
- [Filter By and row filters](../parameters/specificity.md)
- [Saving](../parameters/saving.md)
