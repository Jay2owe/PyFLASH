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

| Parameter | Meaning |
|---|---|
| `dependent_variables` | Outcome columns to model. |
| `predictors` | Predictor/covariate columns. |
| `categorical` | Categorical predictors. Use `auto` to infer text/bool columns, a list of names, or `False`/empty to force numeric treatment. |
| `reference_levels` | Reference category levels, for example `{"Diagnosis": "Control"}`. |
| `interactions` | Interaction terms as tuples such as `("Diagnosis", "Sex")` or formula strings. |
| `medication_columns` | Free-text medication columns that are converted to model flags. |
| `medication_mode` | Medication flag mode: `any`, `tokens`, or `both`. |
| `medication_min_count` | Minimum token count before a medication-specific flag is added. |
| `specificity` | Legacy/internal row filter for this compatibility wrapper. A filter queue returns one result per filter. Prefer [`linear_model`](linear_model.md) with `filter_by` for new analyses. |
| `exclude` | Exclusion rules applied before modelling. |
| `cov_type`, `cov_kwds` | Statsmodels covariance estimator options such as `HC3`. If omitted, ordinary standard errors are used. |
| `alpha` | Confidence/significance cutoff for model summaries. |
| `fdr_method` | Multiple-testing correction method for coefficient p-values, for example `fdr_bh`. |
| `fdr_family` | Coefficient correction family: `all`, `dependent_variable`, or `none`. |
| `save` | If true, write the legacy modelling tables and manifest. |
| `output_dir` | Base directory for saved output. If omitted, PyFLASH uses `batch.data_path`. The run is placed under `Modelling/Linear Models/<run_label>`. |
| `run_label` | Run folder label. Defaults to `linear_models`. |
| `if_exists` | Collision policy: `version`, `overwrite`, or `error`. This wrapper does not support `skip`. |
| `return_fits` | Include fitted statsmodels objects in the return dictionary. These are not saved to disk. |
| `verbose` | Print progress messages. |

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
| `manifest.json` | Legacy run summary and table paths. |

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
