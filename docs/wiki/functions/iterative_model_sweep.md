# iterative_model_sweep

## Summary

`iterative_model_sweep` searches for classifier models that predict a
categorical target, such as diagnosis group, from candidate summary columns.

It tests feature subsets, tries several classifier families, ranks the results
by a scoring metric, saves result tables and figures, and returns the best
fitted estimator.

## Signature

```python
iterative_model_sweep(
    data,
    target,
    data_cols=None,
    predictors=None,
    candidate_predictors=None,
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
)
```

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
| `data` | `Batch` or `pandas.DataFrame` | required | Source data. Legacy positional name: `batch_or_df`. |
| `target` | `str` | required | Categorical column to predict. |
| `data_cols` | list-like or `None` | `None` | Exact candidate predictor columns. Legacy alias: `possible_predictors`. |
| `predictors` | list-like or `None` | `None` | Alias for candidate predictor columns. |
| `candidate_predictors` | list-like or `None` | `None` | Alias for candidate predictor columns. |
| `data_col_contains` | list-like, `str`, or `None` | `None` | Include predictors whose names contain these strings. Legacy alias: `column_strings`. |
| `data_col_regex` | `str` or list-like | `None` | Include predictors matching regex patterns. Legacy alias: `regex_string`. |
| `data_col_exclude` | `str` or list-like | `None` | Exclude predictors by name text. Legacy alias: `predictor_exclude`. |
| `predictor_exclude` | `str` or list-like | `""` | Legacy alias for `data_col_exclude`. |
| `excluded_predictors` | list-like or `None` | `None` | Explicit predictor names to remove. |
| `max_features` | `int` | `2` | Maximum feature subset size to test. |
| `repeat_features` | `bool` | `False` | Allow repeated base features in a subset. |
| `model_preset` | `str` | `"ultra_compact"` | Classifier grid size. Accepted values: `"ultra_compact"`, `"compact"`, `"full"`. |
| `model_families` | list-like or `None` | `None` | Restrict the run to selected classifier families. |
| `class_order` | list-like or `None` | `None` | Explicit class order. Useful for ordered labels such as Control, MCI, AD. |
| `cv` | `str` | `"stratified5"` | Cross-validation scheme. Accepted values: `"stratified5"`, `"stratifiedN"`, or `"loo"`. |
| `scoring` | `str` | `"balanced_accuracy"` | Ranking metric. `log_loss` is treated as lower-is-better. |
| `filter_by` | dict, tuple, list, or `None` | `None` | Optional row filter such as `{"Time": "WeekEight"}`. Legacy alias: `specificity`. A list runs queue mode. |
| `exclude` | rule spec or `None` | `None` | Row exclusion rules applied before modelling. |
| `normalize_method` | `str` | `"zscore"` | Numeric scaling. Accepted values include `"zscore"`, `"minmax"`, and `"none"`. |
| `search_strategy` | `str` | `"exhaustive"` | `"exhaustive"` tests every subset; `"beam"` carries forward only top subsets. |
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
| `parallel_backend` | `str` | `"threads"` | Parallel backend. Accepted values: `"threads"` or `"processes"`. |
| `return_details` | `bool` | `True` | Return full result dictionary. |

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

## Saved Outputs

When `save=True`, the run folder contains:

| File | Meaning |
|---|---|
| `iterative_model_sweep_scores.csv` | All valid model scores. |
| `top_iterative_model_sweep_scores.csv` | Top-ranked score rows. |
| `top_feature_recurrence.csv` | Features that recur among top models. |
| `top_model_predictions.csv` | Fold-level predictions for the best model. |
| `top_model_permutation_test.csv` | Optional permutation-test results. |
| `iterative_model_sweep_scores_partial.csv` | Checkpoint file for long runs. |
| `iterative_model_sweep_scores_partial.meta.json` | Checkpoint compatibility metadata. |
| `manifest.json` | Run settings and key results. |
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
