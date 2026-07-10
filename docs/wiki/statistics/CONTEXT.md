# Statistics Folder Context

This folder explains the statistical ideas and outputs used by PyFLASH. It is
for interpretation and method documentation, not one-callable API pages.

## What Belongs Here

Add pages for recurring statistical behavior:

- `group-comparisons.md`: t tests, one-way ANOVA, Kruskal-Wallis, post-hoc
  tests, planned comparisons, and normality checks.
- `effect-sizes.md`: Cohen's d, Hedges' g, rank-biserial effects, ANOVA
  effects, confidence intervals, and magnitude labels.
- `multiple-testing.md`: Bonferroni, Sidak, false-discovery-rate corrections,
  and when PyFLASH applies them.
- `correlation.md`: correlation methods, gates, significance matrices, and
  matrix differences.
- `linear-models.md`: covariates, adjusted means, coefficients, contrasts, and
  model diagnostics.
- `classification.md`: cross-validation, balanced accuracy, macro F1, AUC,
  log loss, permutation tests, and model sweep interpretation.
- `rhythm.md`: cosinor fits, acrophase, circular statistics, and group tests.
- `power.md`: achieved power, required sample size, and effect-size assumptions.
- `structured-results.md`: report records, describe coverage, and result
  manifests from analyses.

## Page Shape

Use this shape:

```markdown
# Statistical topic

## Summary
Plain-language explanation of the method or result.

## Where PyFLASH Uses It
Functions, plot types, or pipeline outputs.

## Inputs
Required columns, groups, assumptions, or settings.

## Outputs
Tables, figures, report records, or dictionary keys.

## Interpretation
How users should read the result.

## Limitations
Assumptions, small-sample issues, missing data, or caveats.

## See Also
Related functions, parameters, and workflows.
```

## Source Checks

Use these source files:

- `PyFLASH/stats.py`
- `PyFLASH/stats_extra.py`
- `PyFLASH/plotting.py`
- `PyFLASH/pipeline.py`
- `PyFLASH/modelling.py`
- `PyFLASH/report.py`
- tests for the relevant analysis path

Keep wording factual and avoid overclaiming biological interpretation.
