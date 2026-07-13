# Distribution Plots

## Use This When

Use distribution plots when the shape of marker-level values matters more than a
single mean. Histograms, ridgelines, and ECDFs (empirical cumulative
distribution functions) show whether groups differ in spread, skew, tails, or
subpopulations.

These plots are descriptive. They help you decide what is happening in the raw
marker or ROI-level data before summarising it with mean bars or formal tests.

## Input Data

Distribution plots read marker tables, not just `batch.summary`. The input
object must expose `experiment.data[marker].df` with a numeric column that can be
resolved from `x_attr`.

Typical marker-table columns are:

| Column | Purpose |
|---|---|
| `AnimalName` | Subject or animal identity. |
| `Condition` | Group assignment used for condition-level panels. |
| `ROI` or `Region` | Region/ROI metadata used by ROI filters. |
| marker attribute columns | Numeric object, cell, or ROI measurements such as `Area` or `GFAP_Volume`. |

`x_attr` can be a full column name or a marker-specific suffix. For example,
`marker="GFAP", x_attr="Volume"` can resolve to `GFAP_Volume` when that column
exists.

## Main Functions

| Function | Registry name | Best for |
|---|---|---|
| [`plot_histograms`](../functions/plot_histograms.md) | `histograms` | Counting or overlaying binned marker-level values. |
| [`plot_ridgeline`](../functions/plot_ridgeline.md) | `ridgeline` | Comparing smoothed distributions across many groups in one figure. |
| [`plot_ecdf`](../functions/plot_ecdf.md) | `ecdf` | Comparing full cumulative distributions without choosing bins. |

## Common Options

| Option family | Parameters | Use |
|---|---|---|
| Marker and attribute | `marker`, `x_attr` | Choose the marker table and numeric attribute. Scalars or list-like values queue multiple plots. |
| Grouping | `by`, `factor` | Draw by condition or by a factor column. See [conditions and factors](../parameters/conditions-and-factors.md). |
| Row filtering | `filter_by` / `specificity`, `roi` | Restrict rows by metadata or ROI base before plotting. `filter_by` is preferred; `specificity` is the legacy alias. |
| Axes | `x_range`, `xmin`, `xmax`, `share_axes` | Force or share x-axis ranges across related plots. |
| Saving | `save` | Write figures under the object's figure folder. See [saving](../parameters/saving.md). |

Histogram-specific options include `bins`, `binwidth`, `bin_edges`,
`bin_range`, `share_bins`, `kde`, `stat`, `combine`/`merge`, `invert_x`, and
`ymax`.

Ridgeline-specific options include `ridge_height`, `alpha`, `line_width`,
`bw_adjust`, `bottom_ticks`, and `bottom_tick_labels`.

ECDF-specific options include `line_width`, `alpha`, `stat`, `complementary`,
`bottom_ticks`, and `bottom_tick_labels`.

## Outputs

The distribution functions return dictionaries from the shared plotting runner.
Those dictionaries are useful for checking which groups were processed and how
many rows contributed. They do not return long-lived figure handles.

When `save=True`, single-marker distribution figures are written below
`experiment.fig_path` as `<marker>/<plot type>/...`, for example
`GFAP/Histograms`, `GFAP/Ridgelines`, or `GFAP/ECDFs`. Factor and row-filter
contexts are encoded into filename suffixes. When several ROI bases are queued,
the ROI base is prepended as a top-level folder. `plot_histograms` can also
attempt an optional interactive HTML histogram when Altair is installed and
interactive export is enabled in configuration; that HTML branch is controlled
by the interactive export setting rather than only by `save`.

The registry names `histograms`, `ridgeline`, and `ecdf` are describe-layer
exempt: they are descriptive visualisations and do not emit structured
inferential report records.

## Examples

Histogram for one marker attribute:

```python
from PyFLASH.plotting import plot_histograms

result = plot_histograms(
    batch,
    marker="Cells",
    x_attr="Area",
    bins=30,
    save=False,
)

print(result.get("group"))
```

Overlay conditions on one histogram:

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

Compare distribution shapes without bins:

```python
from PyFLASH.plotting import plot_ridgeline, plot_ecdf

plot_ridgeline(batch, marker="GFAP", x_attr="Volume", factor="Diagnosis")
plot_ecdf(batch, marker="GFAP", x_attr="Volume", complementary=True)
```

## Interpretation

Histograms depend on bin choices. Use shared bins when comparing groups.

Ridgelines are good for scanning many groups, but smoothing can hide small
clusters. Adjust `bw_adjust` when distributions look over-smoothed or noisy.

ECDF curves avoid bins: a curve shifted to the right usually indicates larger
values. Complementary ECDFs are useful when the upper tail is the important
feature.

None of these plots corrects for subject-level replication by itself. If you are
making group claims, pair the distribution view with subject-level summaries or a
pipeline that works at the correct experimental unit.

## See Also

- [`plot_histograms`](../functions/plot_histograms.md)
- [`plot_ridgeline`](../functions/plot_ridgeline.md)
- [`plot_ecdf`](../functions/plot_ecdf.md)
- [Mean bars](mean-bars.md)
- [Column selection](../parameters/column-selection.md)
- [Filter By and row filters](../parameters/specificity.md)
- [Figure folders](../outputs/figure-folders.md)
