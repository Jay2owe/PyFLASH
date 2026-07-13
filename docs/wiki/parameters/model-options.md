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

| Parameter | Meaning | Aliases |
|---|---|---|
| `model_preset` | Chooses the classifier grid size. | None. |
| `model_families` | Whitelists classifier families. `None` includes all families available for the preset. | None. |
| `cv` | Chooses cross-validation. | None. |
| `scoring` | Sorts the ranked model table by an output metric column. | `"loss"` normalizes to `"log_loss"`. |
| `search_strategy` | Chooses how feature subsets are searched. | None. |
| `beam_width` | Number of subsets carried forward per level when using beam search. | None. |
| `n_jobs` | Controls joblib parallelism where available. | None. |
| `parallel_backend` | Chooses the joblib backend for parallel scoring. | `"process"` and `"loky"` normalize to the process backend. |
| `random_state` | Seeds shuffled stratified CV and stochastic classifiers. | None. |
| `resume` | Controls whether a matching partial checkpoint is reused when `save=True`. | None. |

#### `model_preset` options

| Option | Behavior |
|---|---|
| `"ultra_compact"` (default) | Runs the smallest built-in grid for quick screens and examples. |
| `"compact"` | Tests a broader grid while keeping runtime moderate. |
| `"full"` | Tests the largest built-in grid and takes longer. |

#### `cv` options

| Option | Behavior |
|---|---|
| `"stratified"` | Uses stratified folds with the default fold count for the workflow. |
| `"stratified5"` (default) | Uses up to five stratified folds, capped by the smallest class count. |
| `"stratifiedN"` | Uses `N` stratified folds, for example `"stratified2"` for two folds. |
| `"loo"` | Uses leave-one-out cross-validation. Aliases: `"leave_one_out"`, `"leave-one-out"`. |

#### `scoring` options

| Option | Behavior |
|---|---|
| `"balanced_accuracy"` | Sorts by balanced accuracy. |
| `"macro_f1"` | Sorts by macro-averaged F1 score. |
| `"accuracy"` | Sorts by raw accuracy. |
| `"macro_ovr_auc"` | Sorts by macro one-vs-rest AUC when that metric is produced. |
| `"log_loss"` | Sorts by log loss. Alias: `"loss"`. |

#### `search_strategy` options

| Option | Behavior |
|---|---|
| `"exhaustive"` (default) | Scores every valid feature subset. |
| `"beam"` | Carries only the best prior subsets at each depth. |

#### `n_jobs` options

| Option | Behavior |
|---|---|
| `1` | Runs subset scoring serially. |
| `-1` | Uses all available cores through joblib where available. |
| Positive integer | Uses that many workers. |

#### `parallel_backend` options

| Option | Behavior |
|---|---|
| `"threads"` (default) | Shares cached numeric matrices and has lower startup overhead. |
| `"processes"` | Uses separate processes, which can help some large sweeps but costs more startup time. Aliases: `"process"`, `"loky"`. |

#### `resume` options

| Option | Behavior |
|---|---|
| `True` | Resumes a matching partial checkpoint when `save=True` and metadata matches. |
| `False` | Starts a fresh sweep. |

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

| Parameter | Meaning | Aliases |
|---|---|---|
| `data_cols` | Outcome variables to model. | `dependent_variables`, `outcomes`. |
| `predictors` | Explanatory variables or formula terms, depending on the function. | None. |
| `categorical` | Controls categorical encoding in linear-model formulas. | None. |
| `reference_levels` | Sets reference categories for categorical predictors. | None. |
| `interactions` | Adds interaction terms to linear models. | None. |
| `alpha` | Significance threshold for FDR and coefficient plots. | None. |
| `fdr_method` | Chooses the multiple-testing correction method for coefficient p-values. | See [Statistics options](statistics-options.md). |
| `cov_type` | Statsmodels covariance estimator type. | `cov_kwds` supplies covariance keyword arguments rather than the estimator name. |

#### `categorical` options

| Option | Behavior |
|---|---|
| `"auto"` (default in supported workflows) | Lets PyFLASH infer categorical predictors. |
| Iterable of names | Treats only the listed predictors as categorical. |

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
