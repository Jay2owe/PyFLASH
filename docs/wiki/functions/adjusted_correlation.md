# adjusted_correlation

## Summary

`adjusted_correlation` runs a two-stage correlation workflow: first it screens
candidate covariates against endpoint columns, then it residualizes endpoints and
runs adjusted correlations on the residuals. It writes both raw and adjusted
correlation outputs, covariate-screening tables, residual-model summaries,
adjusted regression summaries, a manifest, and an overview montage.

Registry name: `adjusted_correlation_pipeline`.

## Signature

```python
from PyFLASH import adjusted_correlation

adjusted_correlation(
    experiment,
    endpoints=None,
    *,
    filtered_columns=None,
    data_cols=None,
    covariates=None,
    candidate_covariates=None,
    categorical="auto",
    reference_levels=None,
    covariate_gate="fdr",
    covariate_alpha=None,
    min_endpoint_hits=1,
    by="all",
    factor=None,
    split_by=None,
    specificity=None,
    filter_by=None,
    save=True,
    tests=("pearsonr", "spearmanr", "kendalltau"),
    require="and",
    gate="p",
    alpha=0.05,
    min_n=3,
    max_adjusted_regressions=None,
    value_matrices="p",
    run_label=None,
    if_exists="overwrite",
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
| `pandas.DataFrame` | Yes | Wrapped internally. Provide group and subject metadata with `group_col`, `group_cols`, `subject_col`, or `dataframe_kwargs` when needed. |

## Parameters

| Parameter | Type | Default | Meaning |
|---|---|---:|---|
| `experiment` | `Batch`, `Experiment`, `MiniExperiment`, or wrapped `DataFrame` | required | Data source containing a numeric summary table. |
| `endpoints` | list-like or `None` | `None` | Endpoint columns to correlate. Aliases: `data_cols`, legacy `filtered_columns`. |
| `covariates` | list-like or `None` | `None` | Columns that are always adjusted for. These stay in the adjustment model and are not screened. |
| `candidate_covariates` | list-like or `None` | `None` | Columns screened against endpoints. Candidates that pass the covariate screen are promoted into the adjustment set and removed from the endpoint matrix. |
| `categorical` | `"auto"`, list-like, `False`, or `None` | `"auto"` | Categorical covariate handling. |
| `reference_levels` | mapping or `None` | `None` | Optional reference categories, for example `{"Diagnosis": "Control"}`. |
| `covariate_gate` | `str` | `"fdr"` | Gate used during candidate screening. |
| `covariate_alpha` | `float` or `None` | `None` | Candidate-screening threshold. `None` reuses `alpha`. |
| `min_endpoint_hits` | `int` | `1` | Minimum number of endpoint associations needed before a candidate covariate is promoted. |
| `by` | `str` | `"all"` | Grouping mode for raw and adjusted correlation blocks. |
| `split_by` | `str`, list-like, or `None` | `None` | Group by one summary-table column or condition factor such as `Diagnosis`. Alias: `factor`. |
| `filter_by` | mapping, tuple, list, or `None` | `None` | Restrict rows before analysis. A list of filters runs queue mode and tags outputs by filter value. Alias: `specificity`. |
| `roi` | `str`, list-like, or `None` | `None` | Restrict to one or more ROI bases. `None` uses the object's default summary. |
| `data_col_contains` | `str`, list-like, or `None` | `None` | Include endpoint columns containing these case-sensitive text fragments. Alias: `column_strings`. |
| `data_col_regex` | `str`, list-like, or `None` | `None` | Include endpoint columns matching one or more Python regular expressions. Alias: `regex_string`. |
| `data_col_exclude` | `str`, list-like, or `None` | `""` | Remove endpoint columns containing these text fragments. The empty-string default excludes nothing. Alias: `exclude`. |
| `tests` | tuple/list of `str` | `("pearsonr", "spearmanr", "kendalltau")` | Correlation methods to run for each endpoint pair. |
| `require` | `str` | `"and"` | Multi-method gate logic for selected endpoint pairs. |
| `gate` | `str` | `"p"` | Gate used for raw and adjusted endpoint-pair selection. Accepts the same p/q gate names as `covariate_gate`. |
| `alpha` | `float` | `0.05` | Endpoint-correlation significance cutoff. Also supplies `covariate_alpha` when that is `None`. |
| `min_n` | `int` | `3` | Minimum complete observations for screening, residual models, and adjusted correlations. |
| `max_adjusted_regressions` | `int` or `None` | `None` | Cap for adjusted regression plot/report rows. `None` means no cap. |
| `tick_label_size` | `int` or `float` | `20` | Tick-label size for saved matrix-style figures. |
| `value_matrices` | `str`, list-like, or `None` | `"p"` | Which p/q heatmap figures to save for each raw/adjusted block. |
| `plot_pvalue_matrices`, `plot_qvalue_matrices` | `bool` or `None` | `None` | Legacy boolean overrides for p/q heatmap saving. `None` follows `value_matrices`. |
| `run_label` | `str` or `None` | `None` | Run folder name. `None` builds a deterministic slug from columns and settings. |
| `if_exists` | `str` | `"overwrite"` | Run-folder collision policy. |
| `save` | `bool` | `True` | Write run files. `False` computes and returns results without clearing or writing a run folder. |
| `write_manifest` | `bool` | `True` | Write `manifest.json` and update `_runs_index.csv` when saving. |
| `verbose` | `bool` | `True` | Print progress messages. |
| `montage` | `bool` | `True` | Create `! Overview Montage.png` in the run folder when saving. |
| `group_col` | `str` or `None` | `None` | Public alias for `condition_col` when wrapping a raw `DataFrame`. If both are omitted, the adapter uses `condition_col="Condition"`. |
| `group_cols` | list-like or `None` | `None` | Crossed grouping columns used when wrapping a raw `DataFrame`. Alias: `factor_cols`. |
| `subject_col` | `str` or `None` | `None` | Public alias for `animal_col` when wrapping a raw `DataFrame`. If both are omitted, the adapter uses `animal_col="AnimalName"`. |
| `group_list` | `groupList` or `None` | `None` | Optional group metadata for raw `DataFrame` input. Aliases: `groups`, legacy `conditions`. |
| `dataframe_kwargs` | `dict` or `None` | `None` | Advanced options forwarded to the raw `DataFrame` adapter. |

## Parameter Options

### `categorical` options

| Option | Behavior |
|---|---|
| `"auto"` (default) | Infer text and boolean columns as categorical covariates. |
| List-like | Treat the named columns as categorical covariates. |
| `False` / empty | Force numeric treatment. |

### `covariate_gate` and `gate` options

| Option | Behavior |
|---|---|
| `"p"` | Use raw p-values. |
| `"fdr"` | Use corrected q-values. Aliases: `"q"`, `"q_value"`, `"q-value"`, `"fdr_bh"`, `"bh"`. |

### `by` options

| Option | Behavior |
|---|---|
| `"all"` (default) | Pool rows for raw and adjusted correlation blocks. |
| `"conditions"` | Run raw and adjusted correlation blocks by resolved group-list condition. |

### `tests` options

| Option | Behavior |
|---|---|
| `"pearsonr"` | Pearson linear correlation. Aliases: `"pearson"`, `"p"`. |
| `"spearmanr"` | Spearman rank correlation. Aliases: `"spearman"`, `"s"`. |
| `"kendalltau"` | Kendall rank correlation. Aliases: `"kendall"`, `"k"`. |

### `require` options

| Option | Behavior |
|---|---|
| `"and"` (default) | Every method in `tests` must pass the selected gate. |
| `"or"` | Any method in `tests` may pass the selected gate. |

### `value_matrices` options

| Option | Behavior |
|---|---|
| `"p"` (default) | Save p-value heatmap figures. |
| `"q"` | Save q-value heatmap figures. |
| `"both"` | Save both p-value and q-value heatmap figures. |
| `"none"` | Skip p/q heatmap figures. |
| List containing `"p"` and/or `"q"` | Save exactly the requested p/q heatmap figure types. |

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
| `pipeline` | `str` | Always `adjusted_correlation`. |
| `run_label`, `fig_dir`, `data_dir` | `str` | Run name and output folders. Tables and figures are co-located in the run folder. |
| `initial_endpoints`, `final_endpoints` | `list[str]` | Endpoint set before and after candidate-covariate promotion. |
| `always_covariates`, `candidate_covariates`, `promoted_covariates`, `final_covariates` | `list[str]` | Covariate sets used by the workflow. |
| `categorical`, `reference_levels` | mixed | Model encoding settings recorded for reproducibility. |
| `covariate_screening` | `pandas.DataFrame` | Candidate covariate associations with endpoints and pass/fail information. |
| `endpoint_status` | `pandas.DataFrame` | Which endpoint columns remained endpoints or became covariates. |
| `residual_models` | `pandas.DataFrame` | Residualization model summaries for each endpoint. |
| `adjusted_regression_coefficients` | `pandas.DataFrame` | Coefficients for residualization and adjusted regression models. |
| `adjusted_regression_summaries` | `pandas.DataFrame` | Model-level adjusted regression summaries. |
| `raw` | `dict` | Raw correlation summary plus `pairwise` and `selected` DataFrames. |
| `adjusted` | `dict` | Adjusted residual-correlation summary plus `pairwise` and `selected` DataFrames. |
| `n_adjusted_regressions` | `int` | Number of adjusted regression summaries/plots generated. |
| `specificity`, `conditions`, `n_conditions` | mixed | Row filter and merged filter-queue ledger when applicable. |
| `montage` | `str` | Path to the overview montage when one was written or reused. |
| `reused` | `bool` | True when `if_exists="skip"` returned an existing manifest. |

When `if_exists="skip"` reuses an existing run, the returned object is the cached
manifest and may not contain the in-memory DataFrames listed above.

## Saved Outputs

With `save=True`, files are written below:

```text
<fig_path>/Adjusted Correlation Pipeline/<run_label>/
```

The run folder is both `fig_dir` and `data_dir`.

| Output | Meaning |
|---|---|
| `covariate_screening*.csv` | Candidate covariate screen results. |
| `endpoint_status*.csv` | Endpoint/covariate status after screening. |
| `residual_models*.csv` | Residualization model summaries. |
| `adjusted_regression_coefficients*.csv` | Coefficient table for adjustment models. |
| `adjusted_regression_summaries*.csv` | Adjusted regression summaries. |
| `pairwise_correlations_Raw*.csv` | Raw endpoint-pair correlation table. |
| `selected_pairs_Raw*.csv` | Raw selected pairs. |
| `pairwise_correlations_Adjusted*.csv` | Adjusted residual-correlation table. |
| `selected_pairs_Adjusted*.csv` | Adjusted selected pairs. |
| `Matrices/coef_<Method>_Raw*.csv` and `Matrices/coef_<Method>_Adjusted*.csv` | Raw and adjusted coefficient matrices. |
| `Matrices/pvalues_<Method>_Raw*.csv` and `Matrices/pvalues_<Method>_Adjusted*.csv` | Raw and adjusted p-value matrices. |
| `Matrices/qvalues_<Method>_Raw*.csv` and `Matrices/qvalues_<Method>_Adjusted*.csv` | Raw and adjusted q-value matrices. |
| `Matrices/*Raw*.svg`, `Matrices/*Adjusted*.svg` | Raw and adjusted heatmaps. |
| `manifest.json` | Stable run summary for reuse and reporting. |
| `../_runs_index.csv` | One-row-per-run index for adjusted-correlation runs; reruns with the same run label replace the matching index row. |
| `! Overview Montage.png` | Overview montage when `montage=True`. |

For a filter queue, child files receive tags such as
`_Diagnosis.Control`, and the combined manifest records each condition in a
`conditions` list.

## Examples

Adjust marker correlations for age and sex:

```python
from PyFLASH import adjusted_correlation

result = adjusted_correlation(
    batch,
    endpoints=["GFAP Mean", "IBA1 Mean", "CK1d Mean"],
    covariates=["Age", "Sex"],
    categorical=["Sex"],
    reference_levels={"Sex": "F"},
    tests=("pearsonr", "spearmanr"),
    gate="fdr",
    value_matrices="both",
    run_label="markers_adjusted_age_sex",
)

print(result["adjusted_regression_summaries"].head())
print(result["adjusted"]["selected"].head())
```

Let PyFLASH promote covariates that associate with at least two endpoints:

```python
result = adjusted_correlation(
    batch,
    data_col_contains="Mean",
    candidate_covariates=["Age", "Weight", "numSections"],
    min_endpoint_hits=2,
    covariate_gate="fdr",
    save=False,
)
```

## Notes

- Candidate covariates promoted by screening are removed from the endpoint
  correlation matrix so they are not analyzed as endpoint pairs.
- Raw and adjusted blocks are both preserved. Use the `raw` and `adjusted`
  nested dictionaries to compare how adjustment changed selected pairs.
- The manifest records stable summaries and output settings. Do not depend on
  private residual-model helper objects.

## See Also

- [correlation](correlation.md)
- [linear_model](linear_model.md)
- [Pipeline manifests](../data-structures/pipeline-manifests.md)
- [Correlation statistics](../statistics/correlation.md)
- [Linear models](../statistics/linear-models.md)
- [Multiple testing](../statistics/multiple-testing.md)
- [Saving](../parameters/saving.md)
- [Filter By](../parameters/specificity.md)
- [API reference](../api-reference.md)
