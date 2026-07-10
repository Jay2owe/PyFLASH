# Correlation

## Summary

Correlation methods estimate association between two numeric variables. PyFLASH
supports Pearson, Spearman, and Kendall correlations in regression plots,
correlation matrices, and correlation pipelines.

## Where PyFLASH Uses It

- [plot_regressions](../functions/plot_regressions.md) draws pairwise scatter
  plots and computes a correlation coefficient and p-value.
- [correlation](../functions/correlation.md) runs matrix-style pairwise
  correlation analysis and writes long tables plus coefficient, p-value,
  q-value, and gate matrices.
- [adjusted_correlation](../functions/adjusted_correlation.md) uses model-based
  adjustment before correlation-style summaries.
- [plot_matrices](../functions/plot_matrices.md),
  [plot_rect_matrices](../functions/plot_rect_matrices.md), and
  [plot_matrix_differences](../functions/plot_matrix_differences.md) display
  correlation-style matrices and differences.

## Inputs

Inputs are numeric columns, optional x/y column sets, optional grouping, a
correlation method, a minimum paired sample size, and a selection gate. PyFLASH
accepts method aliases for Pearson, Spearman, and Kendall.

Rows are evaluated pairwise. A column pair can have enough observations in one
group and too few in another. Underpowered or invalid pairs are kept in matrix
outputs with missing statistics so the missing result is visible.

## Outputs

The correlation pipeline writes:

- `pairwise_correlations*.csv`: long-format coefficient, p-value, q-value, and
  sample-size rows.
- `selected_pairs*.csv`: rows passing the requested selection gate.
- coefficient matrices with unit diagonal where square matrices are valid.
- p-value, q-value, and gate matrices.
- optional regression figures for selected pairs.
- optional matrix-difference outputs when grouped matrix differences are
  requested.
- `manifest.json` with the method, gate, alpha, minimum sample size, groups, and
  selected/plotted pairs.

## Interpretation

Pearson correlation measures linear association on the original numeric scale.
Spearman and Kendall are rank-based and are less tied to linear scale, but they
still describe monotonic ordering rather than causation.

The `gate` decides whether selection uses raw p-values or q-values. The
`require` option controls whether both the probability gate and any additional
condition must pass, or whether either route can select a pair.

For grouped matrix differences, PyFLASH uses a Fisher r-to-z probability test
for Pearson correlations. Spearman and Kendall grouped differences are reported
as descriptive coefficient deltas, not as inferential Fisher tests.

## Limitations

Correlation does not identify cause, mechanism, or direction of effect. Shared
batch effects, repeated measures, outliers, nonlinear patterns, and group
structure can produce strong coefficients that are not direct relationships
between the measured variables.

Rank-based methods can be affected by many tied values. Pearson confidence and
difference logic assumes approximately independent paired observations.

## See Also

- [Multiple Testing](multiple-testing.md)
- [Structured Results](structured-results.md)
- [correlation](../functions/correlation.md)
- [adjusted_correlation](../functions/adjusted_correlation.md)
- [plot_regressions](../functions/plot_regressions.md)
