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

Common public arguments are shown. Internal underscore-prefixed queue arguments
are reserved for PyFLASH.

## Input Object Types

| Object type | Accepted? | Notes |
|---|---:|---|
| `Batch` | Yes | Main input for saved PyFLASH analyses. |
| `Experiment` / `MiniExperiment` | Yes | Works when a summary table and output paths are available. |
| `pandas.DataFrame` | Yes | Wrapped internally. Provide `group_col`, `group_cols`, `subject_col`, or `dataframe_kwargs` when needed. |

## Parameters

| Parameter | Type | Default | Meaning |
|---|---|---:|---|
| `experiment` | `Batch`, `Experiment`, `MiniExperiment`, or wrapped `DataFrame` | required | Data source containing a summary table. |
| `data_cols` | list-like or `None` | `None` | Outcome columns to model. Aliases: `dependent_variables`, `outcomes`. |
| `predictors` | list-like or `None` | `None` | Covariate/predictor columns or supported formula terms. The primary `group` term is added separately when provided. |
| `group` | `str` or `None` | `None` | Primary group column used for adjusted means and group contrasts, for example `Diagnosis`. Aliases: `group_col`; legacy raw-table alias `condition_col`. |
| `categorical` | `"auto"`, list-like, `False`, or `None` | `"auto"` | Categorical predictor handling. The group term is treated as categorical. |
| `reference_levels` | mapping or `None` | `None` | Reference category levels, for example `{"Diagnosis": "Control", "Sex": "F"}`. |
| `interactions` | list-like or `None` | `None` | Interaction terms as tuples such as `("Diagnosis", "Sex")` or formula strings. |
| `medication_columns` | list-like or `None` | `None` | Free-text medication columns that are converted to model flags. |
| `medication_mode` | `str` | `"any"` | Medication flag mode. |
| `medication_min_count` | `int` | `2` | Minimum token count before a medication-specific flag is added. |
| `filter_by` | mapping, tuple, list, or `None` | `None` | Restrict rows before modelling. A list of filters runs queue mode and tags outputs by filter value. Alias: `specificity`. |
| `roi` | `str`, list-like, or `None` | `None` | Restrict to one or more ROI bases. `None` uses the object's default summary. |
| `exclude` | object or `None` | `None` | Exclude rows/values using the modelling exclusion path. |
| `cov_type` | `str` or `None` | `None` | Statsmodels covariance estimator type, such as `"HC3"`. `None` uses ordinary standard errors. |
| `cov_kwds` | mapping or `None` | `None` | Extra keyword options for the selected statsmodels covariance estimator. |
| `alpha` | `float` | `0.05` | Confidence/significance cutoff for model summaries and adjusted-mean intervals. |
| `fdr_method` | `str` | `"fdr_bh"` | Multiple-testing correction method for coefficient p-values. |
| `fdr_family` | `str` | `"all"` | Coefficient correction family. |
| `adjusted_means` | `bool` | `True` | Compute model-adjusted group means. Requires a group column unless disabled. |
| `covariate_profile` | `str` | `"mean_mode"` | Adjusted-mean profile. |
| `adjusted_mean_weights` | `str` | `"equal"` | Categorical weights for reference-grid adjusted means. |
| `adjusted_mean_p_adjust` | `str` | `"holm"` | Multiple-comparison correction for adjusted-mean contrasts, for example `"holm"`, `"fdr_bh"`, `"bonferroni"`, or `"none"`. |
| `adjusted_mean_p_family` | `str` | `"dependent_variable"` | Correction family for adjusted-mean contrasts. |
| `plot_adjusted_means` | `bool` | `True` | Save adjusted-mean plots for each dependent variable. |
| `plot_coefficients` | `bool` | `True` | Save a coefficient forest plot. |
| `coefficient_gate` | `str` | `"p"` | Column used to highlight terms in the coefficient forest. |
| `max_coefficient_terms` | `int` | `60` | Maximum number of coefficient terms shown in the forest plot. |
| `tick_label_size` | `int` or `float` | `20` | Tick-label size for saved model figures. |
| `run_label` | `str` or `None` | `None` | Run folder name. `None` builds a deterministic slug from settings. |
| `if_exists` | `str` | `"overwrite"` | Run-folder collision policy. |
| `save` | `bool` | `True` | Write run files. `False` computes and returns results without clearing or writing a run folder. |
| `write_manifest` | `bool` | `True` | Write `manifest.json` and update `_runs_index.csv` when saving. |
| `montage` | `bool` | `True` | Create `! Overview Montage.png` in the run folder when saving. |
| `verbose` | `bool` | `True` | Print progress messages. |
| `group_cols` | list-like or `None` | `None` | Crossed grouping columns used when wrapping a raw `DataFrame`. Alias: `factor_cols`. |
| `subject_col` | `str` or `None` | `None` | Public alias for `animal_col` when wrapping a raw `DataFrame`. If both are omitted, the adapter uses `animal_col="AnimalName"`. |
| `group_list` | `groupList` or `None` | `None` | Optional group metadata for raw `DataFrame` input. Aliases: `groups`, legacy `conditions`. |
| `dataframe_kwargs` | `dict` or `None` | `None` | Advanced options forwarded to the raw `DataFrame` adapter. |

## Parameter Options

### `categorical` options

| Option | Behavior |
|---|---|
| `"auto"` (default) | Infer text and boolean predictors as categorical. |
| List-like | Treat the named terms as categorical. |
| `False` / empty | Force numeric treatment, except the group term remains categorical. |

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

### `covariate_profile` options

| Option | Behavior |
|---|---|
| `"mean_mode"` (default) | Builds adjusted means at mean numeric covariates and modal categorical covariates. |
| `"reference_grid"` | Builds adjusted means over a reference grid. Alias: `"emm"`. |
| `"observed"` | Builds adjusted means using observed covariate profiles. |

### `adjusted_mean_weights` options

| Option | Behavior |
|---|---|
| `"equal"` (default) | Weights categorical reference-grid cells equally. |
| `"observed"` | Weights categorical reference-grid cells by observed frequencies. |

### `adjusted_mean_p_family` options

| Option | Behavior |
|---|---|
| `"dependent_variable"` (default) | Correct adjusted-mean contrasts within each dependent variable. |
| `"all"` | Correct adjusted-mean contrasts as one family. |

### `coefficient_gate` options

| Option | Behavior |
|---|---|
| `"p"` (default) | Highlight terms by raw p-value. |
| `"fdr"` | Highlight terms by corrected q-value. Alias: `"q"`. |

### `if_exists` options

| Option | Behavior |
|---|---|
| `"overwrite"` (default) | Clear the existing generated run folder, then recompute. |
| `"version"` | Keep the old run and write to the next free suffix such as `_v2`. |
| `"error"` | Raise if the run folder already exists. |
| `"skip"` | Reuse the cached manifest when available instead of recomputing. |

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
| `medication_predictors` | `list[str]` | Generated medication flag columns recorded in the manifest. |
| `adjusted_means_dir` | `str` | Folder containing adjusted-mean tables and figures when saving. |
| `specificity`, `conditions`, `n_conditions` | mixed | Row filter and merged filter-queue ledger when applicable. |
| `montage` | `str` | Path to the overview montage when one was written or reused. |
| `reused` | `bool` | True when `if_exists="skip"` returned an existing manifest. |

When `if_exists="skip"` reuses an existing run, the returned object is the cached
manifest and may not include in-memory DataFrames.

When the `PyFLASH.report` collector is active, `linear_model` also emits one
structured report record per dependent variable with `kind="linear_model"`.
Those records summarize formula, model fit, coefficients, and adjusted means;
they are report side effects, not extra keys in the returned dictionary.

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
| `linear_model_adjusted_means*.csv` | Adjusted means table when enabled. Saved in the run folder for table-only runs, or under `Adjusted Means/` when adjusted-mean figures are written. |
| `linear_model_adjusted_mean_comparisons*.csv` | Adjusted-mean contrast table when available. Saved in the run folder for table-only runs, or under `Adjusted Means/` when adjusted-mean figures are written. |
| `Coefficient Forest*.svg` | Coefficient forest plot when `plot_coefficients=True`. |
| `Adjusted Means/Adjusted Means <outcome>*.svg` | Adjusted-mean figures when `plot_adjusted_means=True`. |
| `manifest.json` | Stable run summary for reuse and reporting. |
| `../_runs_index.csv` | One-row-per-run index for linear-model pipeline runs; reruns with the same run label replace the matching index row. |
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

print(result["model_summaries"].head())
print(result["metadata"].head())
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
- Medication text columns are converted to generated predictors. The generated
  predictor names are recorded in `medication_predictors` and the saved
  manifest.
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
