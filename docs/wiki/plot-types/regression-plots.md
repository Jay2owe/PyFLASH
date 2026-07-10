# Regression Plots

## Use This When

Use regression plots when you need to inspect a fitted relationship between
variables, or when you want to summarize many joint regression models in a
single heatmap.

Use [`plot_regressions`](../functions/plot_regressions.md) for visible pairwise
fits and [`plot_multivariable_regression_matrix`](../functions/plot_multivariable_regression_matrix.md)
when each cell should represent a model such as `outcome ~ predictor_1 +
predictor_2`.

## Input Data

Regression plots read subject-level numeric columns from `.summary`. They accept
`Batch`, `Experiment`, and other experiment-like objects. They also accept raw
`pandas.DataFrame` input when you supply grouping metadata such as `group_col`
and `subject_col`.

Both functions support row filtering through `filter_by`/`specificity` and ROI
selection through `roi` when ROI-specific summaries exist.

## Main Functions

| Function | Registry name | Use |
|---|---|---|
| [`plot_regressions`](../functions/plot_regressions.md) | `regressions` | Scatter plots with fitted lines, one per group or one combined overlay. |
| [`plot_multivariable_regression_matrix`](../functions/plot_multivariable_regression_matrix.md) | `multivariable_regression_matrix` | Heatmap of model metrics across outcomes and predictor sets. |

## Common Options

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

## Outputs

`plot_regressions` returns the plotting-run result dictionary. Each leaf result
contains the group name, correlation coefficient, p-value, and Matplotlib
regression artist. With `save=True`, figures are written under `Regressions/`.

`plot_multivariable_regression_matrix` returns one dictionary entry per panel.
Each panel includes `models`, `values`, `p_values`, `q_values`, and dropped-axis
lists. With `save=True`, it writes one combined SVG under
`Multivariable Regression/Matrices/`.

Both registry entries are describe-layer `covered`: when the PyFLASH report
collector is active, they emit structured correlation or multivariable
regression records.

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

## Interpretation

A regression plot is a visual check of the relationship in the selected rows.
Look at the point cloud, group sizes, and axis scaling before interpreting the
p-value annotation.

The multivariable matrix summarizes model fit, not coefficient direction. Use
the returned `models` dictionary when you need `coefficients`, `n`, `df_model`,
`df_resid`, or rank-deficiency details.

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
