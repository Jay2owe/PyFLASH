# Regression Plots

## Use This When

Use regression plots when you need to inspect a fitted relationship between
variables, or when you want to summarize many joint regression models in a
single heatmap.

Use [`plot_regressions`](../functions/plot_regressions.md) for visible pairwise
fits and [`plot_multivariable_regression_matrix`](../functions/plot_multivariable_regression_matrix.md)
when each cell should be fit from subject-level rows, such as
`outcome ~ predictor_1 + predictor_2`. Use
[`plot_model_result_matrix`](../functions/plot_model_result_matrix.md) when the
model fitting has already happened and you have a long-form result table. Use
[`plot_correlation_contrast`](../functions/plot_correlation_contrast.md) when the
question is how a correlation itself *differs between groups* — e.g. a coupling
that is present in one group and lost in others. Use
[`plot_coefficient_contrast`](../functions/plot_coefficient_contrast.md) for the
same shape of question asked about *slopes* rather than correlations — e.g. a
decline that is steeper in one group than another. The two can disagree when
groups differ in spread, so pick the one matching the claim you are making.

## Input Data

Regression plots read subject-level numeric columns from `.summary`. They accept
`Batch`, `Experiment`, and other experiment-like objects. They also accept raw
`pandas.DataFrame` input when you supply grouping metadata such as `group_col`
and `subject_col`.

Both functions support row filtering through `filter_by`/`specificity` and ROI
selection through `roi` when ROI-specific summaries exist.

`plot_model_result_matrix` also accepts PyFLASH objects, raw `pandas.DataFrame`
tables, CSV paths, and table-like objects. For PyFLASH objects, it can read the
result table from `.summary`, `.summaries`, `.data`, or a named attribute.

## Main Functions

| Function | Registry name | Use |
|---|---|---|
| [`plot_regressions`](../functions/plot_regressions.md) | `regressions` | Scatter plots with fitted lines, one per group or one combined overlay. |
| [`plot_multivariable_regression_matrix`](../functions/plot_multivariable_regression_matrix.md) | `multivariable_regression_matrix` | Heatmap of model metrics across outcomes and predictor sets. |
| [`plot_model_result_matrix`](../functions/plot_model_result_matrix.md) | `model_result_matrix` | Heatmap renderer for precomputed model-result tables. |
| [`plot_correlation_contrast`](../functions/plot_correlation_contrast.md) | `correlation_contrast` | Slopegraph of an `x`-vs-measures correlation across an ordered group factor, with Fisher r-to-z / ACAT omnibus significance vs a reference. |
| [`plot_coefficient_contrast`](../functions/plot_coefficient_contrast.md) | `coefficient_contrast` | Same slopegraph for regression *coefficients* (standardized beta or raw slope), with OLS `x * group` interaction significance vs a reference. |

## Common Options

For the two contrast slopegraphs, `x_axis_width_scale` changes only the plotted
x-axis/data-region width relative to the figure canvas. Lower values pull the
group ticks closer together without changing the total figure size. `node_size`
sets the group-node marker diameter in points. `show_ci=True` draws per-node
confidence intervals by default with short horizontal caps; set `show_ci=False`
to hide them.

`plot_regressions` uses `x` and `y` columns. Either can be a list; list inputs
run a queue of plots. `normalize_x` and `normalize_y` can be `True`, `False`, a
target `(min, max)` range, or `"Z-score"`.

`test` selects the correlation method used for the fitted-pair annotation:
Pearson, Spearman, or Kendall with the same aliases as the matrix functions.
`combine=True` overlays all groups in one axes; otherwise each group is saved as
a separate figure.

`plot_multivariable_regression_matrix` uses `data_cols` for outcomes and
`predictors` for model predictor sets. `predictors` must be a mapping such as
`{"Age terms": ["age", "age_squared"]}`. `value` chooses the heatmap value:
`"r2"`, `"adj_r2"`, `"p"`, or `"q"`.

For R2-like matrix values, the colorbar defaults to `0` through the observed
maximum rounded up to the nearest `0.1`, rather than always `0` to `1`. Use
`palette="Greens"` or another seaborn palette name for sequential model-fit
heatmaps.

`plot_model_result_matrix` uses `row_col`, `group_col`, `profile_col`, and
`value_col` to map a long-form results table into a matrix. `p_col` and `q_col`
add raw/FDR markers to the editable in-cell text. When `group_col` is supplied,
group labels span their profile columns and individual profile labels are shown
below them.

## Outputs

`plot_regressions` returns the plotting-run result dictionary. Each leaf result
contains the group name, correlation coefficient, p-value, and Matplotlib
regression artist. With `save=True`, figures are written under `Regressions/`.

`plot_multivariable_regression_matrix` returns one dictionary entry per panel.
Each panel includes `models`, `values`, `p_values`, `q_values`, and dropped-axis
lists. With `save=True`, it writes one combined SVG under
`Multivariable Regression/Matrices/`.

`plot_model_result_matrix` returns the filtered source table, value matrix,
p/q matrices, annotations, and one record per matrix cell. With `save=True`, it
writes one SVG under `Model Results/`.

All three registry entries are describe-layer `covered`: when the PyFLASH
report collector is active, they emit structured correlation, multivariable
regression, or precomputed model-result records.

## Examples

Pairwise fit per condition:

```python
from PyFLASH.plotting import plot_regressions

fits = plot_regressions(
    batch,
    x="Age",
    y="GFAP_Count",
    normalize_x=False,
    normalize_y=False,
    save=False,
)
```

Multivariable model heatmap:

```python
from PyFLASH.plotting import plot_multivariable_regression_matrix

matrix = plot_multivariable_regression_matrix(
    batch,
    data_cols=["GFAP_Count", "Iba1_Count"],
    predictors={"Age model": ["Age", "AgeSquared"], "Sex": ["SexCode"]},
    split_by="all",
    value="q",
    save=False,
)
```

Precomputed model-result heatmap:

```python
from PyFLASH.plotting import plot_model_result_matrix

matrix = plot_model_result_matrix(
    batch,
    model_table="model_results",
    row_label_col="label",
    group_col="Diagnosis",
    profile_col="predictor",
    value_col="r2",
    palette="Greens",
)
```

## Interpretation

A regression plot is a visual check of the relationship in the selected rows.
Look at the point cloud, group sizes, and axis scaling before interpreting the
p-value annotation.

The multivariable matrix summarizes model fit, not coefficient direction. Use
the returned `models` dictionary when you need `coefficients`, `n`, `df_model`,
`df_resid`, or rank-deficiency details.

The model-result matrix does not fit models; it visualizes the values in the
provided table. Audit the upstream model output before quoting the heatmap.

For pipeline-scale correlation discovery, prefer [`correlation`](../functions/correlation.md)
or [`adjusted_correlation`](../functions/adjusted_correlation.md); those
functions combine matrix screening with selected regression plots and saved
manifests.

## See Also

- [Matrix Plots](matrix-plots.md)
- [Column selection](../parameters/column-selection.md)
- [Groups and factors](../parameters/conditions-and-factors.md)
- [Correlation statistics](../statistics/correlation.md)
- [Linear models](../statistics/linear-models.md)
- [Structured results](../statistics/structured-results.md)
