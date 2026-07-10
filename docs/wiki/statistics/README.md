# Statistics

This section explains the statistical methods PyFLASH uses in plots, pipelines,
model outputs, and structured report records. The pages focus on what PyFLASH
computes, where the results appear, and what can and cannot be concluded from
the output.

| Page | Purpose |
|---|---|
| [Group Comparisons](group-comparisons.md) | Tests for comparing numeric measurements across groups. |
| [Effect Sizes](effect-sizes.md) | Magnitude estimates, confidence intervals, and interpretation labels. |
| [Multiple Testing](multiple-testing.md) | Bonferroni, Holm, Sidak, false discovery rate, and PyFLASH gate behavior. |
| [Correlation](correlation.md) | Pearson, Spearman, Kendall, matrix outputs, and correlation gates. |
| [Linear Models](linear-models.md) | Ordinary least squares models, covariates, coefficients, and adjusted means. |
| [Classification](classification.md) | Cross-validation metrics and model-sweep interpretation. |
| [Rhythm](rhythm.md) | Cosinor, circular phase summaries, and rhythm group tests. |
| [Power](power.md) | Achieved power, required sample size, and minimum detectable effects. |
| [Structured Results](structured-results.md) | Report records, manifests, and describe coverage. |

## General Reading Order

Start with the function or pipeline page for the command you ran, then use these
statistics pages to interpret the columns and decisions in the output tables.
For example, [group_comparison](../functions/group_comparison.md) explains how
to run the pipeline, while [Group Comparisons](group-comparisons.md) explains the
tests and result columns it uses.

## Shared Conventions

PyFLASH reports p-values as evidence against a null model, not as effect size
or biological importance. Corrected p-values or q-values appear only where the
function enables a correction step. Effect sizes and confidence intervals should
be read alongside p-values, group sizes, missing-data handling, and the design of
the experiment.

Most pipeline outputs are written as CSV files plus a `manifest.json` file. Some
functions also emit structured report records when the report collector is
active; see [Structured Results](structured-results.md).

## See Also

- [Statistics options](../parameters/statistics-options.md)
- [Model options](../parameters/model-options.md)
- [Report records](../outputs/report-records.md)
- [Pipeline manifests](../data-structures/pipeline-manifests.md)
