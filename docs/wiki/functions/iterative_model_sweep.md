# iterative_model_sweep

## Summary

`iterative_model_sweep` searches for classifier models that predict a
categorical target, such as diagnosis group, from candidate summary columns.

It tests feature subsets, tries several classifier families, ranks the results
by a scoring metric, saves result tables and figures, and returns the best
fitted estimator.

Registry name: `iterative_model_sweep`.

## Signature

```python
iterative_model_sweep(
    batch_or_df=None,
    target=None,
    possible_predictors=None,
    data_cols=None,
    predictors=None,
    candidate_predictors=None,
    column_strings=None,
    regex_string=None,
    data_col_contains=None,
    data_col_regex=None,
    data_col_exclude=None,
    predictor_exclude="",
    excluded_predictors=None,
    max_features=2,
    repeat_features=False,
    model_preset="ultra_compact",
    model_families=None,
    class_order=None,
    cv="stratified5",
    scoring="balanced_accuracy",
    filter_by=None,
    exclude=None,
    normalize_method="zscore",
    search_strategy="exhaustive",
    beam_width=100,
    save=True,
    output_dir=None,
    run_label="iterative_model_sweep",
    top_n=200,
    permutations=0,
    checkpoint_every=250,
    resume=False,
    plot=True,
    dpi=220,
    random_state=20260708,
    fast_numeric=True,
    n_jobs=1,
    parallel_backend="threads",
    parallel_batch_size=256,
    verbose=True,
    return_details=True,
    data=None,
)
```

Common public arguments are shown. `batch_or_df` is the current source argument
for the input table/object; `data` remains as a trailing compatibility alias.

## Input Object Types

| Object type | Accepted? | Notes |
|---|---:|---|
| `Batch` | Yes | Uses `batch.summary` and `batch.fig_path`. |
| Batch-like object | Yes | Must expose a non-empty `.summary` table. |
| `pandas.DataFrame` | Yes | Use when you already have a prepared table. |
| `Experiment` | Only if batch-like | Must expose `.summary`. |

## Parameters

| Parameter | Type | Default | Meaning |
|---|---|---:|---|
| `batch_or_df` | `Batch` or `pandas.DataFrame` | `None` | Source data. This is the current source name for the first positional argument. |
| `data` | `Batch` or `pandas.DataFrame` | `None` | Compatibility alias for `batch_or_df`; use one or the other. |
| `target` | `str` or `None` | `None` | Categorical column to predict. A real target column is required before the sweep can run. |
| `data_cols` | list-like or `None` | `None` | Exact candidate predictor columns. Aliases: `possible_predictors`, `predictors`, `candidate_predictors`. |
| `data_col_contains` | list-like, `str`, or `None` | `None` | Include predictors whose names contain these strings. Alias: `column_strings`. |
| `data_col_regex` | `str` or list-like | `None` | Include predictors matching regex patterns. Alias: `regex_string`. |
| `data_col_exclude` | `str` or list-like | `None` | Exclude predictors by name text. Alias: `predictor_exclude`, whose legacy default is `""`. |
| `excluded_predictors` | list-like or `None` | `None` | Explicit predictor names to remove. |
| `max_features` | `int` | `2` | Maximum feature subset size to test. |
| `repeat_features` | `bool` | `False` | Allow repeated base features in a subset. |
| `model_preset` | `str` | `"ultra_compact"` | Classifier grid size. |
| `model_families` | list-like or `None` | `None` | Restrict the run to selected classifier families. |
| `class_order` | list-like or `None` | `None` | Explicit class order. Useful for ordered labels such as Control, MCI, AD. |
| `cv` | `str` | `"stratified5"` | Cross-validation scheme. |
| `scoring` | `str` | `"balanced_accuracy"` | Ranking metric. `log_loss` is treated as lower-is-better. |
| `filter_by` | dict, tuple, list, or `None` | `None` | Optional row filter such as `{"Time": "WeekEight"}`. A list runs queue mode. Alias: `specificity`. |
| `exclude` | rule spec or `None` | `None` | Row exclusion rules applied before modelling. |
| `normalize_method` | `str` | `"zscore"` | Numeric scaling. |
| `search_strategy` | `str` | `"exhaustive"` | Feature-subset search strategy. |
| `beam_width` | `int` | `100` | Number of subsets kept per level in beam search. |
| `save` | `bool` | `True` | Save tables, metadata, and figures. |
| `output_dir` | Path-like or `None` | `None` | Override output folder. |
| `run_label` | `str` | `"iterative_model_sweep"` | Run folder label. |
| `top_n` | `int` | `200` | Number of top rows to save and summarize. |
| `permutations` | `int` | `0` | Number of label-permutation tests for the best model. |
| `checkpoint_every` | `int` | `250` | Write partial score checkpoint every N scored models. |
| `resume` | `bool` | `False` | Resume from a compatible partial checkpoint. |
| `plot` | `bool` | `True` | Save summary figures. |
| `random_state` | `int` | `20260708` | Seed for reproducible splits and stochastic models. |
| `fast_numeric` | `bool` | `True` | Use faster numeric matrix path when possible. |
| `n_jobs` | `int` | `1` | Parallel scoring workers. Use `-1` for all cores. |
| `parallel_backend` | `str` | `"threads"` | Parallel backend. |
| `return_details` | `bool` | `True` | Return full result dictionary. |

## Parameter Options

### `model_preset` options

| Option | Behavior |
|---|---|
| `"ultra_compact"` (default) | Runs the smallest built-in grid for quick screens and examples. |
| `"compact"` | Tests a broader grid while keeping runtime moderate. |
| `"full"` | Tests the largest built-in grid and takes longer. |

### `cv` options

| Option | Behavior |
|---|---|
| `"stratified5"` (default) | Uses up to five stratified folds, capped by the smallest class count. |
| `"stratifiedN"` | Uses `N` stratified folds, for example `"stratified2"` for two folds. |
| `"loo"` | Uses leave-one-out cross-validation. Aliases: `"leave_one_out"`, `"leave-one-out"`. |

### `normalize_method` options

| Option | Behavior |
|---|---|
| `"zscore"` (default) | Standardizes numeric predictors. |
| `"minmax"` | Scales numeric predictors to a min-max range. |
| `"none"` | Leaves numeric predictors unscaled. |

### `search_strategy` options

| Option | Behavior |
|---|---|
| `"exhaustive"` (default) | Scores every valid feature subset. |
| `"beam"` | Carries only the best prior subsets at each depth. |

### `parallel_backend` options

| Option | Behavior |
|---|---|
| `"threads"` (default) | Shares cached numeric matrices and has lower startup overhead. |
| `"processes"` | Uses separate processes, which can help some large sweeps but costs more startup time. |

## Model Families

The default local configuration includes these families:

| Family | Meaning |
|---|---|
| `ridge_multinomial_logistic` | Regularised linear logistic regression. |
| `elastic_net_multinomial_logistic` | Logistic regression with mixed ridge/lasso regularisation. |
| `ordinal_logistic` | Ordered-class logistic regression. Requires the optional `mord` package. |
| `shrinkage_lda` | Linear Discriminant Analysis with covariance shrinkage. |
| `regularised_qda` | Quadratic Discriminant Analysis with regularisation. |
| `polynomial_svm` | Degree-2 polynomial Support Vector Machine. |
| `shallow_random_forest` | Shallow random forest. |
| `shallow_gradient_boosting` | Shallow gradient boosting classifier. |

Preset sizes depend on optional packages:

| Preset | Typical configs | Meaning |
|---|---:|---|
| `ultra_compact` | 8 | One representative per family; fastest default. |
| `compact` | 12 | Small hyperparameter grid. |
| `full` | 49 | Wider discovery grid. |

## Returns

With `return_details=True`, returns a dictionary.

| Key | Type | Meaning |
|---|---|---|
| `best_family` | `str` | Winning classifier family. |
| `best_model` | `str` | Winning model configuration. |
| `best_features` | `tuple[str, ...]` | Winning feature subset. |
| `best_score` | `float` | Score used for ranking. |
| `best_metrics` | `dict` | Accuracy, balanced accuracy, macro F1, macro AUC, and log loss when available. |
| `best_estimator` | scikit-learn `Pipeline` | Final fitted preprocessing + classifier pipeline. |
| `class_labels` | `list[str]` | Class labels in model order. |
| `all_model_scores` | `pandas.DataFrame` | Ranked score table for all valid model/subset combinations. |
| `top_feature_recurrence` | `pandas.DataFrame` | Features recurring among top-ranked models. |
| `top_model_predictions` | `pandas.DataFrame` | Cross-validated predictions for the best model. |
| `output_dir` | `str` or `None` | Saved output folder when `save=True`. |

With `return_details=False`, returns the legacy tuple
`(model_config, best_features)`, where `model_config` is the winning model
configuration name and `best_features` is a tuple of selected feature names.

## Saved Outputs

When `save=True`, files are written below:

```text
<output_dir>/
```

If `output_dir` is not supplied, PyFLASH uses:

```text
<batch.fig_path>/Modelling/Model Sweep/<run_label>/
```

For plain DataFrames without a `fig_path`, it falls back to:

```text
<current working directory>/Modelling/Model Sweep/<run_label>/
```

The run folder contains:

| File | Meaning |
|---|---|
| `iterative_model_sweep_scores.csv` | All valid model scores. |
| `top_iterative_model_sweep_scores.csv` | Top-ranked score rows. |
| `top_feature_recurrence.csv` | Features that recur among top models. |
| `top_model_predictions.csv` | Fold-level predictions for the best model. |
| `top_model_permutation_test.csv` | Permutation-test summary for the selected top model. |
| `iterative_model_sweep_scores_partial.csv` | Partial-score checkpoint written during saved runs so interrupted/resumed runs can recover progress. |
| `iterative_model_sweep_scores_partial.meta.json` | Checkpoint compatibility metadata written with the partial-score checkpoint. |
| `manifest.json` | Run settings and key results. |
| `README.md` | Human-readable run summary and reproducibility notes. |
| `top_iterative_model_sweep.png` | Summary plot of top models. |
| `family_by_subset_size_heatmap.png` | Family performance by subset size. |
| `top_feature_recurrence.png` | Feature recurrence plot. |

## Examples

### Small default sweep

```python
from PyFLASH import iterative_model_sweep

result = iterative_model_sweep(
    data=batch,
    target="Diagnosis",
    data_cols=[
        "GFAP Volume",
        "Iba1 Volume",
        "DAPI Count",
    ],
    max_features=2,
)

print(result["best_family"])
print(result["best_features"])
print(result["best_metrics"])
```

### Limit the model families

```python
result = iterative_model_sweep(
    data=batch,
    target="Diagnosis",
    data_col_contains=["Volume", "Count"],
    data_col_exclude="NonColoc",
    max_features=2,
    model_families=[
        "ridge_multinomial_logistic",
        "shrinkage_lda",
        "shallow_random_forest",
    ],
)
```

### Larger sweep with parallel scoring

```python
result = iterative_model_sweep(
    data=batch,
    target="Diagnosis",
    data_col_contains=["Volume", "Count", "Intensity"],
    max_features=3,
    model_preset="compact",
    search_strategy="beam",
    beam_width=200,
    n_jobs=-1,
    resume=True,
)
```

### Predict with the fitted best estimator

```python
best_features = list(result["best_features"])
estimator = result["best_estimator"]

predicted_codes = estimator.predict(batch.summary[best_features])
predicted_labels = [result["class_labels"][int(code)] for code in predicted_codes]
```

## Notes

- This is a discovery screen, not proof of biological causality.
- Use `balanced_accuracy` when class sizes are uneven.
- Use `class_order` when the target classes have a meaningful order.
- `ordinal_logistic` is skipped automatically if `mord` is not installed.
- `beam` search is faster for large predictor pools but can miss the global best
  feature subset.
- Numeric predictors are imputed and scaled inside each cross-validation fold.
  Categorical predictors are imputed and one-hot encoded inside each fold.

## See Also

- [Object model](../object-model.md)
- [iterative_best_fit](iterative_best_fit.md)
- [linear_model](linear_model.md)
- [data_overview](data_overview.md)
- [group_comparison](group_comparison.md)
- [Model sweep outputs](../outputs/model-sweep-outputs.md)
- [Classification](../statistics/classification.md)
