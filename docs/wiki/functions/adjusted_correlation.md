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

Only the public arguments are shown. Internal underscore-prefixed queue arguments
are reserved for PyFLASH.

## Input Object Types

| Object type | Accepted? | Notes |
|---|---:|---|
| `Batch` | Yes | Main input for saved PyFLASH analyses. |
| `Experiment` / `MiniExperiment` | Yes | Works when a summary table and output paths are available. |
| `pandas.DataFrame` | Yes | Wrapped internally. Provide group and subject metadata with `group_col`, `group_cols`, `subject_col`, or `dataframe_kwargs` when needed. |

## Parameters

| Parameter | Meaning |
|---|---|
| `endpoints`, `data_cols`, `filtered_columns` | Endpoint columns to correlate. `endpoints` and `data_cols` are public aliases. |
| `covariates` | Columns that are always adjusted for. |
| `candidate_covariates` | Columns screened against endpoints. Candidates that pass the covariate screen are promoted into the adjustment set and removed from the endpoint matrix. |
| `categorical` | Categorical covariates. Use `auto` to infer text/bool columns, a list of names, or `False`/empty to force numeric treatment. |
| `reference_levels` | Optional reference categories, for example `{"Diagnosis": "Control"}`. |
| `covariate_gate` | Gate used during candidate screening. Use `p` for raw p-values or `fdr`/q-value aliases for corrected q-values. |
| `covariate_alpha` | Candidate-screening threshold. If omitted, `alpha` is reused. |
| `min_endpoint_hits` | Minimum number of endpoint associations needed before a candidate covariate is promoted. |
| `by`, `factor`, `split_by` | Grouping for raw and adjusted correlation blocks. |
| `filter_by`, `specificity`, `roi` | Restrict rows before analysis. `filter_by` is the preferred public name; `specificity` remains supported for older code. A filter queue writes one combined run folder with tagged files and a `conditions` ledger. |
| `tests` | Correlation methods: `pearsonr`, `spearmanr`, and/or `kendalltau`. |
| `require` | `and` requires every method to pass; `or` keeps a pair if any method passes. |
| `gate` | Gate used for raw and adjusted endpoint-pair selection: `p` or FDR/q-value aliases. |
| `alpha` | Endpoint-correlation significance cutoff. |
| `min_n` | Minimum complete observations for screening, residual models, and adjusted correlations. |
| `max_adjusted_regressions` | Cap for adjusted regression plot/report rows. Use `None` for no cap. |
| `value_matrices` | Which p/q heatmaps to save for each raw/adjusted block: `p`, `q`, `both`, or `none`. |
| `plot_pvalue_matrices`, `plot_qvalue_matrices` | Legacy boolean overrides for p/q heatmap saving. |
| `run_label` | Run folder name. If omitted, PyFLASH builds a deterministic slug from columns and settings. |
| `if_exists` | Run-folder collision policy: `overwrite`, `version`, `error`, or `skip`. |
| `save` | If true, write run files. |
| `write_manifest` | Write `manifest.json` and update `_runs_index.csv` when saving. |
| `montage` | If true and saving, create `! Overview Montage.png` in the run folder. |

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
| `../_runs_index.csv` | Append-only index of adjusted-correlation runs. |
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
- The manifest records stable summaries and table paths. Do not depend on
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
