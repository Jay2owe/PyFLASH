# Model Summary Plots

## Use This When

Use these plots when you want a compact numeric-analysis summary rather than a
standard group bar chart or relationship matrix.

This family covers power curves, PCA biplots, volcano plots, and timecourse
growth curves. They help summarize design strength, multicolumn structure,
group-vs-control marker changes, or longitudinal trends.

## Input Data

`plot_volcano`, `plot_marker_pca`, and `plot_timecourse` read a subject-level
summary table from a `Batch` or experiment-like object. They also accept raw
`pandas.DataFrame` input through the DataFrame adapter when grouping and subject
columns are provided.

`plot_power_curve` does not need a data table. Its optional `batch` argument is
used only to resolve a default save folder.

## Main Functions

| Function | Registry name | Use |
|---|---|---|
| [`plot_volcano`](../functions/plot_volcano.md) | `volcano` | Group-vs-control effect and p-value screen across many columns. |
| [`plot_marker_pca`](../functions/plot_marker_pca.md) | `marker_pca` | PCA biplot of subject-level marker profiles. |
| [`plot_timecourse`](../functions/plot_timecourse.md) | `timecourse` | Growth-curve fit by group across an ordered time variable. |
| [`plot_power_curve`](../functions/plot_power_curve.md) | `power_curve` | Statistical power as sample size changes. |

## Common Options

Use [`data_cols`](../parameters/column-selection.md) or discovery filters for
volcano and PCA feature selection. Use [`filter_by`](../parameters/specificity.md)
to focus on one region, timepoint, sex, or diagnosis. `plot_volcano` supports
filter queues; `plot_marker_pca` and `plot_timecourse` apply one filter context
per call.

For volcano plots, `control` chooses the reference group, `p_threshold` controls
the horizontal significance line, and `label_points` controls which marker names
are drawn.

For PCA, `hue_column` chooses point colors and `standardize=True` prevents
large-magnitude measurements from dominating the components.

For timecourse plots, `time_map` maps labels such as `"WeekEight"` to numeric
times, and `model` is `"auto"`, `"linear"`, `"exponential"`, or `"logistic"`.

## Outputs

Volcano returns a plotting-run result and saves one SVG per non-control group
when `save=True`.

PCA, timecourse, and power plots return Matplotlib figures by default. With
`return_data=True`, they also return reusable numeric data: PCA scores/loadings,
timecourse fit dictionaries, or a power table.

`power_curve` is describe-layer `exempt`. `volcano`, `marker_pca`, and
`timecourse` are currently describe-layer `unreviewed`: use their returned
objects or saved figures until structured report records are added.

## Examples

Volcano screen:

```python
from PyFLASH.plotting import plot_volcano

plot_volcano(
    batch,
    data_col_contains=["_Count", "_Volume"],
    control="Control",
    p_threshold=0.05,
)
```

PCA with reusable data:

```python
from PyFLASH.plotting import plot_marker_pca

fig, pca = plot_marker_pca(
    batch,
    data_cols=["GFAP_Count", "Iba1_Count", "NeuN_Count"],
    hue_column="Diagnosis",
    return_data=True,
)
```

Power curve:

```python
from PyFLASH.plotting import plot_power_curve

fig, power = plot_power_curve(
    effect_sizes=(0.5, 0.8),
    n_range=(4, 20),
    observed=0.6,
    observed_n=8,
    return_data=True,
)
```

## Interpretation

Volcano plots are screening plots. They show percent change and unadjusted
p-values for each selected column; do not treat them as a full multiple-testing
pipeline.

PCA shows the dominant axes of variation in the selected numeric columns.
Loadings indicate which columns align with each component; point separation is
descriptive unless followed by a formal model.

Power curves use assumed standardized effects. They help judge design
sensitivity but do not prove that a study is adequately powered for every
marker or model.

Timecourse fits depend on the chosen numeric time mapping and available points.
Check returned fit dictionaries before quoting model parameters.

## See Also

- [Statistics options](../parameters/statistics-options.md)
- [Column selection](../parameters/column-selection.md)
- [Power statistics](../statistics/power.md)
- [Multiple testing](../statistics/multiple-testing.md)
- [Linear models](../statistics/linear-models.md)
