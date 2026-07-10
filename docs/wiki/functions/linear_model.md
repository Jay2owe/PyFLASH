# linear_model

## Summary

`linear_model` is the manifested PyFLASH linear-model pipeline. It fits adjusted
ordinary least-squares models for one or more outcomes, records coefficient and
model-summary tables, optionally computes adjusted group means and adjusted-mean
contrasts, saves coefficient/adjusted-mean figures, writes a manifest, and
creates an overview montage.

Registry name: `linear_model_pipeline`.

## Signature

```python
from PyFLASH import linear_model

linear_model(
    experiment,
    dependent_variables=None,
    data_cols=None,
    outcomes=None,
    predictors=None,
    *,
    group=None,
    group_col=None,
    categorical="auto",
    reference_levels=None,
    interactions=None,
    medication_columns=None,
    medication_mode="any",
    medication_min_count=2,
    specificity=None,
    filter_by=None,
    roi=None,
    exclude=None,
    cov_type=None,
    cov_kwds=None,
    alpha=0.05,
    fdr_method="fdr_bh",
    fdr_family="all",
    adjusted_means=True,
    covariate_profile="mean_mode",
    adjusted_mean_weights="equal",
    adjusted_mean_p_adjust="holm",
    adjusted_mean_p_family="dependent_variable",
    plot_adjusted_means=True,
    plot_coefficients=True,
    coefficient_gate="p",
    run_label=None,
    if_exists="overwrite",
    save=True,
    write_manifest=True,
    montage=True,
    ...
)
```

Only the public arguments are shown. Internal underscore-prefixed queue arguments
are reserved for PyFLASH.

## Input Object Types

| Object type | Accepted? | Notes |
|---|---:|---|
| `Batch` | Yes | Main input for saved PyFLASH analyses. |
| `Experiment` / `MiniExperiment` | Yes | Works when a summary table and output paths are available. |
| `pandas.DataFrame` | Yes | Wrapped internally. Provide `group_col`, `group_cols`, `subject_col`, or `dataframe_kwargs` when needed. |

## Parameters

| Parameter | Meaning |
|---|---|
| `dependent_variables`, `data_cols`, `outcomes` | Outcome columns to model. These are aliases; `data_cols` and `outcomes` are preferred in new code. |
| `predictors` | Covariate/predictor columns. The primary `group` term is added separately when provided. |
| `group`, `group_col` | Primary group column used for adjusted means and group contrasts, for example `Diagnosis`. |
| `categorical` | Categorical predictors. Use `auto` to infer text/bool columns, a list of names, or `False`/empty to force numeric treatment. The group term is treated as categorical. |
| `reference_levels` | Reference category levels, for example `{"Diagnosis": "Control", "Sex": "F"}`. |
| `interactions` | Interaction terms as tuples such as `("Diagnosis", "Sex")` or formula strings. |
| `medication_columns` | Free-text medication columns that are converted to model flags. |
| `medication_mode` | Medication flag mode: `any`, `tokens`, or `both`. |
| `medication_min_count` | Minimum token count before a medication-specific flag is added. |
| `filter_by`, `specificity`, `roi` | Restrict rows before modelling. `filter_by` is the preferred public name; `specificity` remains supported for older code. A filter queue writes one combined run folder with tagged files and a `conditions` ledger. |
| `exclude` | Exclude rows/values using the modelling exclusion path. |
| `cov_type`, `cov_kwds` | Statsmodels covariance estimator options such as `HC3`. If omitted, ordinary standard errors are used. |
| `alpha` | Confidence/significance cutoff for model summaries and adjusted-mean intervals. |
| `fdr_method` | Multiple-testing correction method for coefficient p-values, for example `fdr_bh`. |
| `fdr_family` | Coefficient correction family: `all`, `dependent_variable`, or `none`. |
| `adjusted_means` | Compute model-adjusted group means. Requires a group column unless disabled. |
| `covariate_profile` | Adjusted-mean profile: `mean_mode`, `reference_grid`/`emm`, or `observed`. |
| `adjusted_mean_weights` | For reference-grid adjusted means, use `equal` or `observed` categorical weights. |
| `adjusted_mean_p_adjust` | Multiple-comparison correction for adjusted-mean contrasts, for example `holm`, `fdr_bh`, `bonferroni`, or `none`. |
| `adjusted_mean_p_family` | Correction family for adjusted-mean contrasts: `dependent_variable` or `all`. |
| `plot_adjusted_means` | Save adjusted-mean plots for each dependent variable. |
| `plot_coefficients` | Save a coefficient forest plot. |
| `coefficient_gate` | Column used to highlight terms in the coefficient forest: `p` or `fdr`. |
| `max_coefficient_terms` | Maximum number of coefficient terms shown in the forest plot. |
| `run_label` | Run folder name. If omitted, PyFLASH builds a deterministic slug. |
| `if_exists` | Run-folder collision policy: `overwrite`, `version`, `error`, or `skip`. |
| `save` | If true, write run files. |
| `write_manifest` | Write `manifest.json` and update `_runs_index.csv` when saving. |
| `montage` | If true and saving, create `! Overview Montage.png`. |

## Returns

The function returns a dictionary. For a fresh run it contains manifest keys plus
in-memory tables:

| Key | Type | Meaning |
|---|---|---|
| `pipeline` | `str` | Always `linear_model`. |
| `run_label`, `fig_dir`, `data_dir` | `str` | Run name and output folders. Tables and figures are co-located in the run folder. |
| `group`, `predictors`, `covariates`, `model_terms` | mixed | Resolved modelling terms after aliases, medication flags, and interactions. |
| `dependent_variables` | `list[str]` | Outcomes fitted by the pipeline. |
| `categorical`, `reference_levels`, `interactions` | mixed | Encoding and formula settings. |
| `coefficients` | `pandas.DataFrame` | Coefficient table with estimates, intervals, p-values, and corrected q-values where configured. |
| `model_summaries` | `pandas.DataFrame` | Model-level summaries such as fit statistics and observation counts. |
| `metadata` | `pandas.DataFrame` | Per-model metadata, formulas, resolved columns, and fit status. |
| `adjusted_means_table` | `pandas.DataFrame` | Adjusted group means when `adjusted_means=True`. |
| `adjusted_mean_comparisons` | `pandas.DataFrame` | Pairwise adjusted-mean contrasts when available. |
| `n_adjusted_means`, `n_adjusted_mean_comparisons` | `int` | Adjusted-mean table counts. |
| `medication_predictors`, `medication_metadata` | mixed | Generated medication flags and supporting metadata. |
| `adjusted_means_dir` | `str` | Folder containing adjusted-mean tables and figures when saving. |
| `specificity`, `conditions`, `n_conditions` | mixed | Row filter and merged filter-queue ledger when applicable. |
| `montage` | `str` | Path to the overview montage when one was written or reused. |
| `reused` | `bool` | True when `if_exists="skip"` returned an existing manifest. |

When `if_exists="skip"` reuses an existing run, the returned object is the cached
manifest and may not include in-memory DataFrames.

## Saved Outputs

With `save=True`, files are written below:

```text
<fig_path>/Linear Model Pipeline/<run_label>/
```

The run folder is both `fig_dir` and `data_dir`.

| Output | Meaning |
|---|---|
| `linear_model_coefficients*.csv` | Coefficient table. |
| `linear_model_summaries*.csv` | Model-level summaries. |
| `linear_model_metadata*.csv` | Formulas, resolved terms, and fit metadata. |
| `Adjusted Means/linear_model_adjusted_means*.csv` | Adjusted means table when enabled. |
| `Adjusted Means/linear_model_adjusted_mean_comparisons*.csv` | Adjusted-mean contrast table when available. |
| `Coefficient Forest*.svg` | Coefficient forest plot when `plot_coefficients=True`. |
| `Adjusted Means/Adjusted Means <outcome>*.svg` | Adjusted-mean figures when `plot_adjusted_means=True`. |
| `manifest.json` | Stable run summary for reuse and reporting. |
| `../_runs_index.csv` | Append-only index of linear-model pipeline runs. |
| `! Overview Montage.png` | Overview montage when `montage=True`. |

For the older table-only workflow, see
[run_linear_model_pipeline](run_linear_model_pipeline.md).

## Examples

Fit adjusted models and adjusted means for diagnosis:

```python
from PyFLASH import linear_model

result = linear_model(
    batch,
    outcomes=["Total counts", "Amplitude"],
    group="Diagnosis",
    predictors=["Age", "Sex", "sleep treatment"],
    categorical=["Sex"],
    reference_levels={"Diagnosis": "Control", "Sex": "F"},
    interactions=[("Diagnosis", "Sex")],
    run_label="diagnosis_adjusted_models",
)
```

Fit model tables only, without adjusted means or saved files:

```python
result = linear_model(
    batch,
    data_cols=["Amplitude"],
    predictors=["Age", "Sex"],
    adjusted_means=False,
    plot_adjusted_means=False,
    plot_coefficients=False,
    save=False,
)
```

## Notes

- `adjusted_means=True` or `plot_adjusted_means=True` needs a primary group
  column. Disable both for a covariate-only model run.
- `covariate_profile="emm"` is accepted as an alias for the reference-grid
  estimated marginal means path.
- Medication text columns are converted to generated predictors; check
  `medication_metadata` before interpreting coefficients.
- The saved manifest summarizes stable outputs. Statsmodels fit objects are not
  part of the stable pipeline output contract.

## See Also

- [run_linear_model_pipeline](run_linear_model_pipeline.md)
- [adjusted_correlation](adjusted_correlation.md)
- [group_comparison](group_comparison.md)
- [Pipeline manifests](../data-structures/pipeline-manifests.md)
- [Linear models](../statistics/linear-models.md)
- [Model options](../parameters/model-options.md)
- [Saving](../parameters/saving.md)
- [Filter By](../parameters/specificity.md)
- [API reference](../api-reference.md)
