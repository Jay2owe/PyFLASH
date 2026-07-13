# run_linear_model_pipeline

## Summary

`run_linear_model_pipeline` is the compatibility wrapper for the original
table-only linear-model workflow. It fits the same adjusted linear-model backend
used by the modern [linear_model](linear_model.md) pipeline, but it writes only
legacy modelling tables and a manifest under `Modelling/Linear Models`.

New saved analyses should generally use [linear_model](linear_model.md), which
also writes pipeline run folders, adjusted means, figures, run indexes, and
montages.

## Signature

```python
from PyFLASH import run_linear_model_pipeline

run_linear_model_pipeline(
    batch,
    dependent_variables,
    predictors,
    *,
    categorical="auto",
    reference_levels=None,
    interactions=None,
    medication_columns=None,
    medication_mode="any",
    medication_min_count=2,
    specificity=None,
    exclude=None,
    cov_type=None,
    cov_kwds=None,
    alpha=0.05,
    fdr_method="fdr_bh",
    fdr_family="all",
    save=True,
    output_dir=None,
    run_label="linear_models",
    if_exists="version",
    return_fits=False,
    verbose=True,
)
```

## Input Object Types

| Object type | Accepted? | Notes |
|---|---:|---|
| `Batch` | Yes | Main supported input. |
| Batch-like object | Yes | Must expose a non-empty `.summary` DataFrame and, when saving without `output_dir`, a usable `data_path`. |
| `pandas.DataFrame` | No | Use `linear_model` if you need raw DataFrame adapter support. |

## Parameters

| Parameter | Type | Default | Meaning |
|---|---|---:|---|
| `batch` | `Batch` or batch-like object | required | Data source with a non-empty `.summary` table and, when saving without `output_dir`, a usable `data_path`. |
| `dependent_variables` | list-like | required | Outcome columns to model. |
| `predictors` | list-like | required | Predictor/covariate columns or supported formula terms. |
| `categorical` | `"auto"`, list-like, `False`, or `None` | `"auto"` | Categorical predictor handling. |
| `reference_levels` | mapping or `None` | `None` | Reference category levels, for example `{"Diagnosis": "Control"}`. |
| `interactions` | list-like or `None` | `None` | Interaction terms as tuples such as `("Diagnosis", "Sex")` or formula strings. |
| `medication_columns` | list-like or `None` | `None` | Free-text medication columns that are converted to model flags. |
| `medication_mode` | `str` | `"any"` | Medication flag mode. |
| `medication_min_count` | `int` | `2` | Minimum token count before a medication-specific flag is added. |
| `specificity` | mapping, tuple, list, or `None` | `None` | Legacy/internal row filter for this compatibility wrapper. A filter queue returns one result per filter. Prefer [`linear_model`](linear_model.md) with `filter_by` for new analyses. |
| `exclude` | object or `None` | `None` | Exclusion rules applied before modelling. |
| `cov_type` | `str` or `None` | `None` | Statsmodels covariance estimator type, such as `"HC3"`. `None` uses ordinary standard errors. |
| `cov_kwds` | mapping or `None` | `None` | Extra keyword options for the selected statsmodels covariance estimator. |
| `alpha` | `float` | `0.05` | Confidence/significance cutoff for model summaries. |
| `fdr_method` | `str` | `"fdr_bh"` | Multiple-testing correction method for coefficient p-values. |
| `fdr_family` | `str` | `"all"` | Coefficient correction family. |
| `save` | `bool` | `True` | Write the legacy modelling tables and manifest. |
| `output_dir` | Path-like or `None` | `None` | Base directory for saved output. `None` uses `batch.data_path`; the run is placed under `Modelling/Linear Models/<run_label>`. |
| `run_label` | `str` | `"linear_models"` | Run folder label. |
| `if_exists` | `str` | `"version"` | Collision policy. This wrapper does not support `"skip"`. |
| `return_fits` | `bool` | `False` | Include fitted statsmodels objects in the return dictionary. These are not saved to disk. |
| `verbose` | `bool` | `True` | Print progress messages. |

## Parameter Options

### `categorical` options

| Option | Behavior |
|---|---|
| `"auto"` (default) | Infer text and boolean predictors as categorical. |
| List-like | Treat the named terms as categorical. |
| `False` / empty | Force numeric treatment. |

### `medication_mode` options

| Option | Behavior |
|---|---|
| `"any"` (default) | Creates a flag for any listed medication. |
| `"tokens"` | Creates medication-specific token flags. |
| `"both"` | Creates both the any-medication flag and token-specific flags. |

### `fdr_method` options

| Option | Behavior |
|---|---|
| `"fdr_bh"` (default) | Benjamini-Hochberg FDR correction. |
| `"fdr_by"` | Benjamini-Yekutieli FDR correction. |
| `"holm"` | Holm family-wise correction. |
| `"bonferroni"` | Bonferroni family-wise correction. |
| `"sidak"` | Sidak family-wise correction. |

### `fdr_family` options

| Option | Behavior |
|---|---|
| `"all"` (default) | Correct coefficient p-values as one family. |
| `"dependent_variable"` | Correct within each dependent variable. |
| `"none"` | Do not apply coefficient FDR correction. |

### `if_exists` options

| Option | Behavior |
|---|---|
| `"version"` (default) | Keep the old run and write to the next free suffix such as `_v2`. |
| `"overwrite"` | Clear the existing generated run folder, then recompute. |
| `"error"` | Raise if the run folder already exists. |

## Returns

The function returns a dictionary:

| Key | Type | Meaning |
|---|---|---|
| `coefficients` | `pandas.DataFrame` | Coefficient table with estimates, intervals, p-values, and corrected q-values where configured. |
| `model_summaries` | `pandas.DataFrame` | Model-level summaries such as fit statistics and observation counts. |
| `metadata` | `pandas.DataFrame` | Formulas, resolved terms, and fit status. |
| `formulas` | `dict` | Model formulas by dependent variable. |
| `predictors` | `list[str]` | Resolved predictor columns. |
| `categorical`, `reference_levels` | mixed | Encoding settings used for the models. |
| `medication_predictors`, `medication_metadata` | mixed | Generated medication flags and supporting metadata. |
| `run_label`, `output_dir` | `str` | Saved run label and folder when saving. |
| `fits` | `dict` | Fitted statsmodels objects, only when `return_fits=True`. |

If the legacy `specificity` row filter is a queue, the function returns a
dictionary keyed by each filter value, with each value containing that filter's
normal return object. Prefer [`linear_model`](linear_model.md) with `filter_by`
for new analyses.

## Saved Outputs

With `save=True`, files are written below:

```text
<output_dir or batch.data_path>/Modelling/Linear Models/<run_label>/
```

| Output | Meaning |
|---|---|
| `linear_model_coefficients.csv` | Coefficient table. |
| `linear_model_summaries.csv` | Model-level summaries. |
| `linear_model_metadata.csv` | Formulas, resolved terms, and fit metadata. |
| `manifest.json` | Legacy run settings and model metadata. |

This wrapper does not write adjusted-mean tables, figures, `_runs_index.csv`, or
`! Overview Montage.png`.

## Examples

Table-only legacy run:

```python
from PyFLASH import run_linear_model_pipeline

result = run_linear_model_pipeline(
    batch,
    dependent_variables=["Total counts", "Amplitude"],
    predictors=["Age", "Sex", "sleep treatment"],
    categorical=["Sex"],
    reference_levels={"Sex": "F"},
    run_label="linear_models_age_sex",
)
```

Return fit objects for interactive inspection without saving:

```python
result = run_linear_model_pipeline(
    batch,
    dependent_variables=["Amplitude"],
    predictors=["Age", "Sex"],
    save=False,
    return_fits=True,
)

fit = result["fits"]["Amplitude"]
print(fit.summary())
```

## Notes

- This wrapper exists for backward compatibility with notebooks that expect
  `Modelling/Linear Models` outputs.
- The modern [linear_model](linear_model.md) pipeline is the better choice when
  you need adjusted means, plots, manifests indexed with other pipelines, or
  montages.
- `return_fits=True` is for Python-side inspection. Fit objects are not part of
  the stable saved-output contract.

## See Also

- [linear_model](linear_model.md)
- [iterative_best_fit](iterative_best_fit.md)
- [Linear models](../statistics/linear-models.md)
- [Model options](../parameters/model-options.md)
- [Saving](../parameters/saving.md)
- [Filter By](../parameters/specificity.md)
- [API reference](../api-reference.md)
