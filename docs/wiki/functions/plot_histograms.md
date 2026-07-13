# plot_histograms

## Summary

`plot_histograms` draws histograms for marker-level values from
`experiment.data[marker].df`. It is registered as `histograms` in
`PyFLASH.spec.PLOT_REGISTRY`.

Use it to inspect raw object, cell, ROI, or marker distributions before reducing
the data to subject-level summaries.

## Example figure

<!-- gallery-example-code:start -->
Gallery render call (after `ex = build_example_data(fig_path=TMP)`, `exp = ex.experiment`, and `P = PyFLASH.plotting`):

```python
P.plot_histograms(exp, marker="Marker1", x_attr="Volume", combine=True, save=True)
```
<!-- gallery-example-code:end -->

![plot_histograms example figure](../gallery/images/plot_histograms.svg)

*`Marker1` volume distribution, groups A/B/C overlaid. Rendered from the [synthetic example dataset](../examples/README.md).*

## Signature

```python
plot_histograms(
    experiment,
    marker,
    x_attr,
    by="conditions",
    factor=None,
    bins=30,
    binwidth=None,
    kde=False,
    alpha=0.5,
    stat="count",
    merge=False,
    combine=False,
    invert_x=False,
    ymax=None,
    save=True,
    specificity=None,
    filter_by=None,
    roi=None,
    bin_range=None,
    bin_edges=None,
    share_bins=False,
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
| `marker` | `str` or list-like | required | Marker table key. Tolerant matching accepts exact keys, case-insensitive keys, or one unambiguous prefix. List-like values queue plots. |
| `x_attr` | `str` or list-like | required | Attribute to plot. May be a full marker-table column or a marker suffix such as `"Volume"`. List-like values queue plots. |
| `by` | `str` | `"conditions"` | Iteration level. |
| `factor` | `str` or `None` | `None` | Group by factor values instead of conditions. |
| `bins` | `int` or sequence | `30` | Number of bins, unless `bin_edges` or `binwidth` supplies a more specific bin definition. |
| `binwidth` | number or `None` | `None` | Fixed bin width passed to Seaborn. |
| `kde` | `bool` | `False` | Overlay a kernel density estimate. |
| `alpha` | number | `0.5` | Bar transparency. |
| `stat` | `str` | `"count"` | Histogram statistic. |
| `combine` | `bool` | `False` | Overlay all groups in one combined figure instead of saving one figure per group. Alias: `merge`. |
| `invert_x` | `bool` | `False` | Reverse the x-axis. |
| `ymax` | number or `None` | `None` | Manual y-axis upper limit. Must be finite and greater than zero when supplied. |
| `save` | `bool` | `True` | Save SVG figures under the input object's figure folder. |
| `filter_by` | dict, tuple, queue, or `None` | `None` | Row filter applied before plotting. A queue returns a dictionary keyed by filter. Alias: `specificity`. |
| `roi` | `str`, list-like, or `None` | `None` | ROI-base selector. Multiple ROI bases run queue mode. |
| `bin_range` | `(min, max)` or `None` | `None` | Explicit histogram range. |
| `bin_edges` | sequence or `None` | `None` | Exact bin edges. Overrides automatic bin computation. |
| `share_bins` | `bool` | `False` | Use one shared set of bin edges across separate group figures. `combine=True` always shares bins. |
| `xmin`, `xmax` | number or `None` | `None` | Convenience aliases for lower/upper values in `bin_range`. |
| `share_axes` | `bool` | `True` | Use registered axis limits when available and no explicit range is supplied. |

## Parameter Options

### `by` options

| Option | Behavior |
|---|---|
| `"conditions"` (default) | Iterate over resolved conditions/groups. |

### `stat` options

| Option | Behavior |
|---|---|
| `"count"` (default) | Plot raw counts per bin. |
| `"frequency"` | Plot frequency per bin. |
| `"probability"` | Plot probability per bin. |
| `"percent"` | Plot percent per bin. |
| `"density"` | Plot density per bin. |

## Returns

| Return value | Type | Meaning |
|---|---|---|
| result | `dict` | Shared runner output. Keys commonly include `histogram`, `condition`, and `group`, each mapping to lists collected during iteration. |
| queued result | `dict` | When `marker`, `x_attr`, `filter_by`, or `roi` is queued, returns nested dictionaries keyed by the queued values. |

The normal return value is an execution summary, not a persistent Matplotlib
figure handle. Use saved SVG files for the rendered plots.

## Saved Outputs

When `save=True`, figures are written below `experiment.fig_path` under
`<marker>/Histograms/`, for example `GFAP/Histograms`. Factor and row-filter
contexts are encoded into filename suffixes. When several ROI bases are queued,
the ROI base is prepended as a top-level folder.

Common filenames are:

```text
<x column> Histogram <group>.svg
<x column> Histogram (Combined).svg
```

If Altair is installed and interactive HTML export is enabled, PyFLASH attempts
to write an optional `interactive_histogram.html` in the histogram output folder.
This HTML export is controlled by the interactive-export configuration, not just
by the `save` flag.

## Examples

### Plot one marker attribute

```python
from PyFLASH.plotting import plot_histograms

result = plot_histograms(
    batch,
    marker="Cells",
    x_attr="Area",
    bins=30,
    save=False,
)

print(result.keys())
```

### Overlay groups in one figure

```python
plot_histograms(
    batch,
    marker="GFAP",
    x_attr="Volume",
    combine=True,
    stat="density",
    share_bins=True,
)
```

### Queue several attributes

```python
queued = plot_histograms(
    batch,
    marker="GFAP",
    x_attr=["Volume", "MeanIntDen"],
    bin_range=(0, 500),
    save=False,
)

print(queued.keys())  # ("GFAP", "Volume"), ("GFAP", "MeanIntDen")
```

### Reuse the returned summary

```python
result = plot_histograms(batch, marker="Cells", x_attr="Area", save=False)

for group in result.get("group", []):
    print(group)
```

## Notes

- `marker` resolves against `experiment.data` and raises if the match is missing
  or ambiguous.
- `x_attr` can be a suffix, a full raw column, or a display-name alias resolved
  from the marker table.
- `combine=True` is best for direct group overlays. Use `share_bins=True` when
  saving separate group histograms that should be comparable.
- `histograms` is describe-layer exempt: it is a descriptive distribution plot
  and does not emit structured inferential report records.

## See Also

- [Distribution plots](../plot-types/distribution-plots.md)
- [`plot_ridgeline`](plot_ridgeline.md)
- [`plot_ecdf`](plot_ecdf.md)
- [Groups and factors](../parameters/conditions-and-factors.md)
- [Filter By and row filters](../parameters/specificity.md)
- [Saving](../parameters/saving.md)
