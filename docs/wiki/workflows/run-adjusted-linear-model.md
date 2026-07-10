# Run Adjusted Linear Model

## Goal

Fit adjusted linear models for one or more outcomes, then save coefficient
tables, model summaries, adjusted group means, adjusted-mean contrasts, figures,
a manifest, and an overview montage.

Use [`linear_model`](../functions/linear_model.md) for new adjusted-model
workflows. Use [`adjusted_correlation`](../functions/adjusted_correlation.md)
when the question is residualized correlations, not adjusted means.

## Inputs

- A `Batch`, experiment-like object, `DataFrameExperiment`, or raw DataFrame.
- Outcome columns through `data_cols`, `outcomes`, or `dependent_variables`.
- A primary group column when adjusted means are wanted, such as `Diagnosis`.
- Predictor/covariate columns such as `Age`, `Sex`, or `sleep treatment`.
- Categorical/reference-level choices for interpretable coefficients.

## Minimal Path

```python
from PyFLASH import linear_model, load_state

batch = load_state(r"C:\path\to\pickles\SCN_Diagnosis.pkl")

result = linear_model(
    batch,
    data_cols=["Total counts"],
    group="Diagnosis",
    predictors=["Age", "Sex"],
    categorical=["Sex"],
    reference_levels={"Diagnosis": "Control", "Sex": "Female"},
    save=False,
)

print(result["coefficients"].head())
print(result["adjusted_means_table"].head())
```

## Full Workflow

1. Confirm the outcome, group, and predictor columns exist:

```python
needed = ["Total counts", "Amplitude", "Diagnosis", "Age", "Sex"]
print(batch.summary[needed].head())
```

2. Start with a dry run. This catches formula, categorical, and missing-column
   issues before writing files.

```python
dry = linear_model(
    batch,
    outcomes=["Total counts", "Amplitude"],
    group="Diagnosis",
    predictors=["Age", "Sex", "sleep treatment"],
    categorical=["Sex"],
    reference_levels={"Diagnosis": "Control", "Sex": "Female"},
    interactions=[("Diagnosis", "Sex")],
    save=False,
)

print(dry["model_summaries"])
print(dry["adjusted_mean_comparisons"])
```

3. Choose adjusted-mean behavior. The default profile is `mean_mode`; estimated
   marginal means use `covariate_profile="emm"` or `"reference_grid"`.

```python
emm = linear_model(
    batch,
    data_cols=["Total counts"],
    group="Diagnosis",
    predictors=["Age", "Sex"],
    categorical=["Sex"],
    reference_levels={"Diagnosis": "Control"},
    covariate_profile="emm",
    adjusted_mean_weights="equal",
    save=False,
)
```

4. Save a reproducible run folder:

```python
saved = linear_model(
    batch,
    outcomes=["Total counts", "Amplitude"],
    group="Diagnosis",
    predictors=["Age", "Sex", "sleep treatment"],
    categorical=["Sex"],
    reference_levels={"Diagnosis": "Control", "Sex": "Female"},
    interactions=[("Diagnosis", "Sex")],
    run_label="diagnosis_adjusted_models",
    if_exists="version",
    save=True,
)

print(saved["fig_dir"])
print(saved["adjusted_means_dir"])
```

5. Run model-only tables when no group-adjusted means are needed:

```python
model_only = linear_model(
    batch,
    data_cols=["Amplitude"],
    predictors=["Age", "Sex"],
    categorical=["Sex"],
    adjusted_means=False,
    plot_adjusted_means=False,
    plot_coefficients=False,
    save=False,
)
```

6. Use `filter_by` to model a row subset or queue. Pipeline queues share one run
   folder and tag each filter's files.

```python
female_male = linear_model(
    batch,
    data_cols=["Total counts"],
    group="Diagnosis",
    predictors=["Age"],
    filter_by=[
        {"Sex": "Female"},
        {"Sex": "Male"},
    ],
    run_label="diagnosis_by_sex_models",
)
```

## Outputs

With `save=True`, the run folder is:

```text
<batch.fig_path>/Linear Model Pipeline/<run_label>/
```

Common outputs include:

| Output | Meaning |
|---|---|
| `linear_model_coefficients.csv` | Estimates, intervals, p-values, and corrected q-values. |
| `linear_model_summaries.csv` | Model-level fit summaries and counts. |
| `linear_model_metadata.csv` | Resolved formulas, terms, and fit status. |
| `Adjusted Means/linear_model_adjusted_means.csv` | Model-adjusted group means. |
| `Adjusted Means/linear_model_adjusted_mean_comparisons.csv` | Pairwise adjusted-mean contrasts. |
| `Coefficient Forest.svg` | Coefficient summary figure. |
| `Adjusted Means/*.svg` | Adjusted-mean figures by outcome. |
| `manifest.json` | Stable run summary. |
| `../_runs_index.csv` | One-row-per-run index for linear-model runs. |
| `! Overview Montage.png` | Overview montage when saving and montage capture is enabled. |

The Python result dictionary also includes the same tables as in-memory
DataFrames for fresh runs.

## Troubleshooting

- `linear_model adjusted means need group=<column>`: pass a group column, or
  set both `adjusted_means=False` and `plot_adjusted_means=False`.
- Categorical levels look wrong: pass `categorical=[...]` and
  `reference_levels={...}` explicitly.
- A predictor is missing because of display-name changes: inspect
  `batch.summary.columns`; PyFLASH resolves some aliases but not arbitrary Excel
  labels.
- Too many coefficient terms in the forest plot: use `max_coefficient_terms` or
  narrow the predictor set.
- Need legacy table-only outputs under `Modelling/Linear Models`: use
  [`run_linear_model_pipeline`](../functions/run_linear_model_pipeline.md).

## Next Steps

- [linear_model reference](../functions/linear_model.md)
- [run_linear_model_pipeline reference](../functions/run_linear_model_pipeline.md)
- [Linear models statistics](../statistics/linear-models.md)
- [Model options](../parameters/model-options.md)
- [Pipeline run folders](../outputs/pipeline-run-folders.md)
- [Filter By](../parameters/specificity.md)
- [adjusted_correlation reference](../functions/adjusted_correlation.md)
