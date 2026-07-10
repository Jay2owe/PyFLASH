# Linear Models

## Summary

PyFLASH linear-model pipelines fit ordinary least squares models for numeric
dependent variables. They are used to estimate group terms, covariate terms,
interactions, adjusted means, and model summaries across one or more endpoints.

## Where PyFLASH Uses It

- [linear_model](../functions/linear_model.md) is the main pipeline for
  covariate-adjusted ordinary least squares analysis.
- [run_linear_model_pipeline](../functions/run_linear_model_pipeline.md) is the
  legacy wrapper for the same modelling path.
- [plot_multivariable_regression_matrix](../functions/plot_multivariable_regression_matrix.md)
  displays multivariable regression summaries.
- [iterative_model_sweep](../functions/iterative_model_sweep.md) is separate
  classification/discovery modelling; see [Classification](classification.md).

## Inputs

Inputs include one or more dependent variables, a modelling formula or term
lists, optional group terms, predictors, interaction terms, categorical
settings, reference levels, row filters, and sentinel values to exclude.

Categorical handling can be automatic. Object, category, and boolean columns are
treated as categorical by default, and the configured group term is categorical.
Numeric predictors stay numeric unless explicitly converted.

Rows with missing values in the dependent variable or required model terms are
dropped for that model. Sentinel values are filtered before fitting and recorded
in summary metadata.

## Outputs

Linear-model outputs include:

- coefficient tables with estimates, standard errors, t-values, p-values,
  confidence intervals, q-values, and rejection flags.
- model-summary tables with sample counts, dropped rows, R-squared, adjusted
  R-squared, model degrees of freedom, residual degrees of freedom, F-statistic,
  AIC, and BIC.
- model metadata describing formulas, terms, categorical handling, covariance
  settings, and filters.
- optional adjusted-mean tables and adjusted-mean contrast tables.
- adjusted-mean figures and coefficient summary figures.
- report records when structured reporting is active.
- `manifest.json` describing the run.

## Interpretation

A coefficient estimates the expected change in the dependent variable for a
one-unit change in a numeric predictor or relative to a reference level for a
categorical predictor, conditional on the other model terms.

Adjusted means estimate group-level means after applying the configured
reference-grid or observed-profile strategy. Their contrasts are often easier to
read for group questions than raw model coefficients, especially when several
covariates are present.

Robust covariance options change standard errors and p-values, not the fitted
mean structure. Q-values in coefficient tables reflect the configured false
discovery rate family.

## Limitations

Linear models are associative unless the experimental design supports causal
interpretation. Collinearity, small group sizes, sparse categorical levels,
outliers, nonlinear relationships, and complete-case filtering can change
estimates and uncertainty.

Adjusted means depend on the chosen profile and weighting mode. They should not
be mixed with raw group means without noting how they were computed.

## See Also

- [Multiple Testing](multiple-testing.md)
- [Structured Results](structured-results.md)
- [linear_model](../functions/linear_model.md)
- [Model options](../parameters/model-options.md)
