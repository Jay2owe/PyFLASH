# Mean Bars

## Use This When

Use mean bars when you want a compact group summary for one or more
subject-level summary columns. The plot answers questions such as "is this
marker higher in AD than control?" or "which condition has the larger average
count?" while still showing the individual subject points when requested.

For a purely descriptive first pass, mean bars are often the fastest plot to
read. For a distribution-first view, use [distribution plots](distribution-plots.md).
For effect-size summaries across many markers, use
[group comparison plots](group-comparison-plots.md).

## Input Data

Mean bars use summary-table data: one row per subject/animal and one numeric
column per marker or measurement. A normal imported `Batch` or `Experiment`
already has this as `summary`.

Required columns are usually:

| Column | Purpose |
|---|---|
| `AnimalName` | Subject or animal identity used for point means. |
| `Condition` | Main group assignment. |
| selected data columns | Numeric measurements to plot. |

Raw `pandas.DataFrame` input is supported by the plotting function when you
provide `group_col` and `subject_col`, or a full `groupList`.

## Main Functions

| Function | Registry name | What it draws |
|---|---|---|
| [`plot_mean_bars`](../functions/plot_mean_bars.md) | `mean_bars` | One bar chart per selected summary column, with optional subject points and statistical annotations. |

## Common Options

| Option family | Parameters | Use |
|---|---|---|
| Column selection | `data_cols`, `data_col_contains`, `data_col_regex`, `data_col_exclude` | Choose the summary columns to plot. See [column selection](../parameters/column-selection.md). |
| Row filtering | `filter_by` / `specificity`, `roi` | Restrict the rows or ROI base before plotting. |
| Grouping | `split_by` / `factor`, `group_col`, `group_cols` | Plot by the main group list or by one factor in a crossed design. See [groups and factors](../parameters/conditions-and-factors.md). |
| Point display | `points`, `point_fill`, `point_edge`, `point_size`, `point_linewidth` | Control whether and how individual observations are overlaid. |
| Statistics | `comparisons`, `force_nonparametric`, `posthoc`, `posthoc_correction`, `multiple_comparison`, `ns` | Control group tests and annotations. |
| Saving | `save`, `save_normality`, `normality_dpi`, `dry_run` | Write figures/statistics, save normality checks, or compute statistics without rendering. See [saving](../parameters/saving.md). |

`auto_style=True` is useful for crossed designs where two groups share a color.
It automatically varies fill or hatch styles so conditions remain visually
distinct.

## Outputs

`plot_mean_bars` returns the shared plotting-run result dictionary. In
`dry_run=True` mode, it returns a `pandas.DataFrame` of computed statistics
without drawing figures.

When `save=True`, PyFLASH writes SVG bar plots below the object's figure folder,
normally in a `Bars` subfolder. When statistics are run, CSV files are saved next
to the bar SVGs. When `save_normality=True`, normality-check PNGs can also be
written next to the corresponding plot.

`mean_bars` is classified as describe-layer covered: when the report collector
is armed, the shared statistics engine emits structured comparison records.

## Examples

Plot one exact summary column:

```python
from PyFLASH.plotting import plot_mean_bars

result = plot_mean_bars(
    batch,
    data_cols=["GFAP_Count"],
    save=False,
)

print(result.keys())
```

Find columns by name fragments and save the figures:

```python
plot_mean_bars(
    batch,
    data_col_contains=["GFAP", "Iba1"],
    data_col_exclude="Raw",
    comparisons=["1-2"],
    posthoc="Dunn",
    posthoc_correction="Bonferroni",
)
```

Use a raw table:

```python
plot_mean_bars(
    df,
    data_cols=["GFAP_Count"],
    group_col="Diagnosis",
    subject_col="Subject ID",
    save=False,
)
```

## Interpretation

Bars show group means, not the whole distribution. Use the overlaid points to
check group size and spread. A small group with one extreme point can move a
mean substantially, so read the points and statistics CSV together.

Statistical annotations are pairwise tests chosen by the shared PyFLASH
statistics path. If you need a many-marker result table with effect sizes,
multiple-testing control, manifests, and optional superplots, use the
[`group_comparison`](../functions/group_comparison.md) pipeline.

## See Also

- [`plot_mean_bars`](../functions/plot_mean_bars.md)
- [Distribution plots](distribution-plots.md)
- [Group comparison plots](group-comparison-plots.md)
- [Column selection](../parameters/column-selection.md)
- [Groups and factors](../parameters/conditions-and-factors.md)
- [Statistics options](../parameters/statistics-options.md)
- [Normality outputs](../outputs/normality-outputs.md)
