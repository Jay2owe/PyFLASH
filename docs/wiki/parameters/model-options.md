# Model Options

## Summary

Model options control cross-validation, classifier families, feature-subset
search, reproducibility, and output behavior in PyFLASH modelling workflows.
This page covers the shared vocabulary; model-specific interpretation belongs
in the modelling function pages and statistics pages.

## Used By

- [`iterative_model_sweep`](../functions/iterative_model_sweep.md), the main
  classifier feature-subset sweep.
- [`iterative_best_fit`](../functions/iterative_best_fit.md), the iterative
  linear formula search.
- [`linear_model`](../functions/linear_model.md), the adjusted linear-model
  pipeline.
- [`run_linear_model_pipeline`](../functions/run_linear_model_pipeline.md), the
  compatibility wrapper for table-only linear models.
- Model-summary plot families that read model outputs.

## Accepted Values

### Classifier Sweep Options

| Parameter | Accepted values | Behavior |
|---|---|---|
| `model_preset` | `"ultra_compact"`, `"compact"`, or `"full"`. | Chooses the classifier grid size. Larger grids test more hyperparameters and take longer. |
| `model_families` | `None` or a list of built-in family names. | Whitelists classifier families. `None` includes all families available for the preset. |
| `cv` | `"stratified"`, `"stratified5"`, `"stratifiedN"` such as `"stratified2"`, or `"loo"` / `"leave_one_out"` / `"leave-one-out"`. | Chooses cross-validation. Stratified folds are capped by the smallest class count and require at least two samples per class. |
| `scoring` | Common output metric columns such as `"balanced_accuracy"`, `"macro_f1"`, `"accuracy"`, `"macro_ovr_auc"`, or `"log_loss"`; `"loss"` normalizes to `"log_loss"`. | Sorts the ranked model table. Unknown names do not create a new metric; use a metric column produced by the sweep. |
| `search_strategy` | `"exhaustive"` or `"beam"`. | Exhaustive scores every valid subset. Beam keeps the best prior subsets at each depth. |
| `beam_width` | Positive integer. | Number of subsets carried forward per level when `search_strategy="beam"`. |
| `n_jobs` | Integer; `1` serial, `-1` all cores through joblib where available. | Parallelizes subset scoring. |
| `parallel_backend` | `"threads"` or `"processes"` / `"process"` / `"loky"`. | Threads share cached numeric matrices; processes can help some large sweeps but cost more startup time. |
| `random_state` | Integer. | Seeds shuffled stratified CV and stochastic classifiers. |
| `resume` | `True` or `False`. | Resumes a matching partial checkpoint when `save=True`. |

Built-in classifier family names:

| Family |
|---|
| `ridge_multinomial_logistic` |
| `elastic_net_multinomial_logistic` |
| `ordinal_logistic` |
| `shrinkage_lda` |
| `regularised_qda` |
| `polynomial_svm` |
| `shallow_random_forest` |
| `shallow_gradient_boosting` |

`ordinal_logistic` depends on the optional `mord` package. If it is unavailable,
that family is skipped. If `model_families` selects no usable configurations,
PyFLASH raises a `ValueError`.

### Linear Model Options

| Parameter | Accepted values | Behavior |
|---|---|---|
| `dependent_variables` / `data_cols` / `outcomes` | List of outcome columns. | Variables to model. |
| `predictors` | List of predictor columns or formula terms, depending on the function. | Explanatory variables. |
| `categorical` | `"auto"` or iterable of categorical predictor names. | Controls categorical encoding in linear-model formulas. |
| `reference_levels` | Mapping from categorical predictor to reference level. | Sets reference categories. |
| `interactions` | Iterable of interaction specs. | Adds interaction terms to linear models. |
| `alpha` | Float. | Significance threshold for FDR and coefficient plots. |
| `fdr_method` | Multiple-testing method such as `"fdr_bh"` or `"holm"`. | Adjusts coefficient p-values. |
| `cov_type` / `cov_kwds` | Statsmodels covariance options. | Advanced linear-model covariance settings. |

## Examples

Small classifier sweep:

```python
from PyFLASH import iterative_model_sweep

result = iterative_model_sweep(
    batch,
    target="Diagnosis",
    data_cols=["GFAP_Count", "Iba1_Count", "Age"],
    model_preset="ultra_compact",
    model_families=["ridge_multinomial_logistic"],
    cv="stratified2",
    scoring="balanced_accuracy",
    max_features=2,
    save=False,
)
```

Beam search for a larger predictor pool:

```python
result = iterative_model_sweep(
    batch,
    target="Diagnosis",
    data_col_contains=["_Count", "_VolumeTotal"],
    excluded_predictors=["AnimalName", "Condition"],
    max_features=4,
    search_strategy="beam",
    beam_width=50,
    n_jobs=-1,
    random_state=20260708,
)
```

Adjusted linear model:

```python
from PyFLASH import linear_model

result = linear_model(
    batch,
    data_cols=["GFAP_Count"],
    predictors=["Diagnosis", "Sex", "Age"],
    categorical=["Diagnosis", "Sex"],
    reference_levels={"Diagnosis": "Control"},
)
```

## Interactions

Predictor selection shares names with column selection but has modelling-specific
rules. Classifier sweeps use real DataFrame columns. Linear-model functions may
accept formula-like terms through their modelling path.

`cv` and `random_state` interact: stratified CV shuffles with the given seed,
while leave-one-out does not need a random split.

`resume=True` only resumes when a saved partial checkpoint and matching metadata
exist. If the data, predictor set, model grid, CV, scoring, search strategy, or
filter settings differ, PyFLASH starts a fresh checkpoint.

`output_dir` overrides the model-sweep output location. Without it, saved model
sweeps use the batch figure path under `Modelling/Model Sweep/<run_label>/`, or
the current working directory if no batch figure path exists.

## Common Errors

- Passing class labels with fewer than two classes after filtering.
- Asking for stratified CV when one class has fewer than two samples.
- Misspelling a `model_families` name, leaving no classifier configurations.
- Using formula terms such as `C(Sex)` in `iterative_model_sweep`; classifier
  sweeps require real columns.
- Expecting `resume=True` to reuse a checkpoint after changing the model
  settings.
- Setting `n_jobs` high for a tiny sweep, where parallel overhead can dominate.

## See Also

- [Column selection](column-selection.md)
- [Filter By and row filters](specificity.md)
- [Classification statistics](../statistics/classification.md)
- [Linear models](../statistics/linear-models.md)
- [Model sweep outputs](../outputs/model-sweep-outputs.md)
