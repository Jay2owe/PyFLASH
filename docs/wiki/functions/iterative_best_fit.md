# iterative_best_fit

## Summary

`iterative_best_fit` searches feature subsets for a linear regression model. It
tests candidate predictor combinations for one dependent variable, scores them
with leave-one-out or grouped leave-one-out error, reports the best formula and
parameters, and can save diagnostic/insight figures.

This is a modelling function, not a manifested pipeline. It does not write
pipeline manifests, run indexes, or montages.

## Signature

```python
from PyFLASH import iterative_best_fit

iterative_best_fit(
    batch,
    dependent_variable,
    repeat_features=False,
    max_features=0,
    possible_predictors=None,
    data_col_contains=None,
    data_col_regex=None,
    data_col_exclude=None,
    normalize_method="minmax",
    excluded_predictors=None,
    hue_column="Condition",
    color_by=None,
    palette=None,
    save=True,
    dpi=600,
    plot=True,
    return_details=False,
    specificity=None,
    filter_by=None,
    exclude=None,
    cv_group_column="AnimalName",
    cv_backend="fast",
    plot_insights=True,
    top_n_single_predictors=3,
    search_strategy="exhaustive",
    beam_width=100,
    batch_chunk_size=5000,
    ...
)
```

## Input Object Types

| Object type | Accepted? | Notes |
|---|---:|---|
| `Batch` | Yes | Main supported input. Uses `batch.summary` and `batch.fig_path` for saved plots. |
| `Experiment` / `MiniExperiment` | Yes | Works when a summary table and figure path are available. |
| `pandas.DataFrame` | Yes | Wrapped internally. Provide `group_col`, `group_cols`, `subject_col`, or `dataframe_kwargs` when needed. |

## Parameters

| Parameter | Meaning |
|---|---|
| `dependent_variable` | Outcome column to predict. |
| `possible_predictors` | Explicit candidate predictor columns. |
| `data_col_contains`, `data_col_regex`, `data_col_exclude` | Candidate predictor selection helpers. Legacy aliases are `column_strings`, `regex_string`, and `predictor_exclude`. |
| `excluded_predictors` | Explicit candidate columns to remove after selection. |
| `repeat_features` | Allow multiple predictors from the same marker/prefix family in one subset. |
| `max_features` | Maximum feature-subset size. `0` lets PyFLASH choose from the candidate set. |
| `normalize_method` | Predictor normalization: `minmax`, `zscore`, or `none`. |
| `hue_column`, `color_by`, `palette` | Group/color settings for diagnostic plots. `color_by` aliases `hue_column`. |
| `filter_by`, `specificity` | Restrict rows before modelling. `filter_by` is the preferred public name; `specificity` remains supported for older code. A filter queue returns one result per filter. |
| `exclude` | Exclusion rules applied before modelling. |
| `cv_group_column` | Column used for grouped cross-validation folds, commonly `AnimalName`. |
| `cv_backend` | Cross-validation backend: `fast`, `ultra`, or `statsmodels`. |
| `search_strategy` | `exhaustive` tests all subsets; `beam` keeps only the best prior subsets at each depth. |
| `beam_width` | Number of subsets retained per depth when `search_strategy="beam"`. |
| `batch_chunk_size` | Chunk size for vectorized/batched scoring. |
| `plot` | Create diagnostic plots. |
| `plot_insights` | Create feature-addition insight plots. |
| `top_n_single_predictors` | Number of top single predictors highlighted in the insight output. |
| `save` | Save plots to disk when plotting is enabled. |
| `dpi` | Figure resolution for saved raster elements. |
| `return_details` | Return a detailed result dictionary instead of the legacy `(formula, params)` tuple. |

## Returns

By default, the function returns a tuple:

| Position | Type | Meaning |
|---|---|---|
| `0` | `str` | Best model formula. |
| `1` | `pandas.Series` | Best-fit model parameters. |

With `return_details=True`, it returns a dictionary:

| Key | Type | Meaning |
|---|---|---|
| `best_model` | `str` | Best formula. |
| `best_subset` | `tuple[str, ...]` | Predictor subset selected for the best model. |
| `best_score` | `float` | Best cross-validated mean absolute error. Lower is better. |
| `best_params` | `pandas.Series` | Best-fit coefficients. |
| `best_fit` | model object | Fitted statsmodels result for the best model. |
| `cv_params`, `cv_actual`, `cv_predicted` | mixed | Cross-validation outputs used for diagnostics. |
| `cv_fold_mae` | `pandas.DataFrame` | Fold-level mean absolute error table. |
| `cv_group_column`, `cv_backend`, `cv_backend_requested` | mixed | Cross-validation settings and resolved backend. |
| `combinations_tested`, `valid_models_tested` | `int` | Search counts. |
| `search_strategy` | `str` | `exhaustive` or `beam`. |
| `specificity`, `exclude` | mixed | Applied filters/exclusions. |
| `top_single_predictors` | `list[dict]` | Top single-predictor summaries as records (from `DataFrame.to_dict(orient="records")`). |
| `single_model_scores` | `pandas.DataFrame` | Single-predictor model scores. |
| `feature_addition_summary` | `pandas.DataFrame` | How often adding each feature improved score. |
| `all_model_scores` | `pandas.DataFrame` | Model score table for tested subsets. |

If `filter_by` / `specificity` is a queue, the function returns a dictionary
keyed by each filter value, with each value containing that filter's normal
return object.

## Saved Outputs

`iterative_best_fit` only saves figures. It does not save CSV tables,
`manifest.json`, `_runs_index.csv`, or `! Overview Montage.png`.

With `save=True` and `plot=True`, figures are written below:

```text
<fig_path>/Modelling/
```

When a row filter is supplied, PyFLASH adds a filter subfolder/tag using the
same naming helpers as other modelling plots.

| Output | Meaning |
|---|---|
| `Best Iterative Model for <dependent_variable>*.svg/.png` | Main best-fit diagnostic figure. |
| Per-predictor diagnostic figures | Plots for selected and top predictor relationships when generated. |
| Feature-addition insight figures | Optional insight figures when `plot_insights=True`. |

All detailed result tables are returned in memory when `return_details=True`; if
you need persisted tables and manifests, use [iterative_model_sweep](iterative_model_sweep.md)
for classification sweeps or [linear_model](linear_model.md) for manifested
linear models.

## Examples

Legacy tuple return:

```python
from PyFLASH import iterative_best_fit

formula, params = iterative_best_fit(
    batch,
    dependent_variable="Amplitude",
    possible_predictors=["Age", "GFAP Mean", "IBA1 Mean"],
    max_features=2,
    save=False,
)
```

Detailed search with beam pruning:

```python
result = iterative_best_fit(
    batch,
    dependent_variable="Amplitude",
    data_col_contains=["Mean", "Volume"],
    excluded_predictors=["Amplitude"],
    normalize_method="zscore",
    search_strategy="beam",
    beam_width=200,
    return_details=True,
    save=False,
)

print(result["best_model"])
print(result["best_score"])
```

## Notes

- This function is useful for exploratory regression feature selection. It is not
  a substitute for a pre-specified inferential model.
- `beam` search is faster for large predictor pools but can miss the global best
  subset.
- Grouped cross-validation uses `cv_group_column` to keep rows from the same
  subject/animal together.
- Saved figures and returned details are intentionally separate: disabling
  `save` does not prevent the model search from returning results.

## See Also

- [linear_model](linear_model.md)
- [run_linear_model_pipeline](run_linear_model_pipeline.md)
- [iterative_model_sweep](iterative_model_sweep.md)
- [Linear models](../statistics/linear-models.md)
- [Model options](../parameters/model-options.md)
- [Column selection](../parameters/column-selection.md)
- [Input objects](../parameters/input-objects.md)
- [Saving](../parameters/saving.md)
- [Filter By](../parameters/specificity.md)
- [API reference](../api-reference.md)
