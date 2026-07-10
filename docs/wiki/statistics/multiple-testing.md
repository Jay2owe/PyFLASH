# Multiple Testing

## Summary

Multiple-testing corrections adjust interpretation when many hypotheses are
tested in the same analysis. PyFLASH uses corrections in screening pipelines,
post-hoc comparisons, model coefficient tables, adjusted-mean contrasts, rhythm
screens, and correlation matrices.

## Where PyFLASH Uses It

- [group_comparison](../functions/group_comparison.md) can add q-values when
  `screen=True`.
- [correlation](../functions/correlation.md) writes p-value and q-value matrices
  for pairwise correlations.
- [linear_model](../functions/linear_model.md) applies false discovery rate
  correction to coefficient tables and configurable adjustment to adjusted-mean
  contrasts.
- [rhythm](../functions/rhythm.md) can add q-values across screened rhythm or
  parameter tests.
- Kruskal-Wallis post-hoc comparisons can use Bonferroni correction depending
  on the number of pairwise tests.

## Inputs

Multiple-testing steps need a family of p-values. The family defines which tests
are corrected together. PyFLASH defaults vary by workflow:

- Group-comparison screening usually corrects across markers within each
  comparison.
- Correlation pipelines correct across selected pairwise tests within a matrix
  context.
- Linear-model coefficients default to a global family unless another family
  mode is requested.
- Adjusted-mean contrasts can be corrected by dependent variable or across all
  contrasts.
- Rhythm screening corrects across the screened columns or tested parameters.

The `gate` parameter controls which probability column is used to mark a result
as selected or significant. `gate="p"` uses raw p-values. `gate="fdr"` uses
q-values and requires a screen or correction step that actually creates q-values.

## Outputs

Common corrected outputs include:

- `q` or `q_value`: false discovery rate adjusted p-values.
- `reject_fdr`: boolean result from the selected false discovery rate method.
- `p_adjusted` and `reject_adjusted`: adjusted-mean contrast outputs.
- `significant`: workflow-level selection using the requested gate and alpha.
- p-value, q-value, and gate matrices in correlation pipeline output folders.

The raw p-value is retained in PyFLASH outputs even when a corrected column is
added.

## Interpretation

False discovery rate correction controls the expected proportion of false
discoveries among selected results under the method assumptions. Bonferroni,
Sidak, and Holm-style corrections are more family-wise error oriented and are
often stricter when many tests are present.

A result can have `p < alpha` but fail the q-value gate after correction. In
that case, PyFLASH keeps the raw p-value but does not mark the result as
selected under an FDR gate.

## Limitations

Corrections are only as meaningful as the family definition. Changing which
markers, pairs, model terms, or groups are included changes the corrected
values. Screening many possible outputs and then reporting only selected ones
can still overstate certainty if the selection process is not described.

Different workflows use different default correction families because their
tables answer different questions. Check the pipeline manifest and output
columns before comparing q-values across unrelated runs.

## See Also

- [Group Comparisons](group-comparisons.md)
- [Correlation](correlation.md)
- [Linear Models](linear-models.md)
- [Rhythm](rhythm.md)
- [Statistics options](../parameters/statistics-options.md)
