# correlation

## Summary

`correlation` runs the full correlation-discovery pipeline over numeric summary
columns. It computes pairwise correlation tables, coefficient/p-value/q-value
matrices, gate summaries, optional regression plots for selected pairs, optional
between-group matrix differences, a JSON manifest, and an overview montage.

Registry name: `correlation_pipeline`.

## Signature

```python
from PyFLASH import correlation

correlation(
    experiment,
    filtered_columns=None,
    data_cols=None,
    against_columns=None,
    against_data_cols=None,
    by="all",
    factor=None,
    split_by=None,
    specificity=None,
    filter_by=None,
    roi=None,
    save=True,
    tests=("pearsonr", "spearmanr", "kendalltau"),
    require="and",
    gate="p",
    alpha=0.05,
    min_n=3,
    max_regressions=12,
    regression_factor=None,
    regression_test="pearsonr",
    value_matrices="p",
    plot_difference_matrices=False,
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
| `Batch` | Yes | Main input for saved PyFLASH analyses. Uses `batch.summary`, `fig_path`, and `data_path`. |
| `Experiment` / `MiniExperiment` | Yes | Works when a summary table and output paths are available. |
| `pandas.DataFrame` | Yes | Wrapped internally. Provide `group_col`, `group_cols`, `subject_col`, or `dataframe_kwargs` when grouping or saving needs metadata. |

## Parameters

| Parameter | Type | Default | Meaning |
|---|---|---:|---|
| `experiment` | `Batch`, `Experiment`, `MiniExperiment`, or wrapped `DataFrame` | required | Data source containing a numeric summary table. |
| `data_cols` / `filtered_columns` | list-like or `None` | `None` | Exact first-axis columns. `filtered_columns` is the legacy alias. If omitted, PyFLASH discovers usable numeric columns. |
| `against_data_cols` / `against_columns` | list-like or `None` | `None` | Optional second-axis columns. `None` runs a square all-vs-all matrix; supplying columns runs a rectangular matrix. |
| `data_col_contains` / `column_strings` | `str`, list-like, or `None` | `None` | Include first-axis columns containing these case-sensitive text fragments. |
| `data_col_regex` / `regex_string` | `str`, list-like, or `None` | `None` | Include first-axis columns matching one or more Python regular expressions. |
| `data_col_exclude` / `exclude` | `str`, list-like, or `None` | `""` | Remove first-axis columns containing these text fragments. The empty-string default excludes nothing. |
| `against_data_col_contains` / `against_column_strings` | `str`, list-like, or `None` | `None` | Substring selector for the optional second axis. |
| `against_data_col_regex` / `against_regex_string` | `str`, list-like, or `None` | `None` | Regex selector for the optional second axis. |
| `against_data_col_exclude` / `against_exclude` | `str`, list-like, or `None` | `""` | Exclusion selector for the optional second axis. |
| `by` | `str` | `"all"` | Grouping mode. Accepted values include `"all"` to pool rows and `"conditions"` to run by group list. |
| `factor` / `split_by` | `str`, list-like, or `None` | `None` | Group by one summary-table column or condition factor such as `Diagnosis`; `split_by` is the newer public name. |
| `filter_by` / `specificity` | mapping, tuple, list, or `None` | `None` | Restrict rows before analysis. A list of filters runs queue mode and tags outputs by filter value. |
| `roi` | `str`, list-like, or `None` | `None` | Restrict to one or more ROI bases. `None` uses the object's default summary. |
| `tests` | tuple/list of `str` | `("pearsonr", "spearmanr", "kendalltau")` | Correlation methods. Accepted values: `"pearsonr"`, `"spearmanr"`, `"kendalltau"` and common aliases `"pearson"`/`"p"`, `"spearman"`/`"s"`, `"kendall"`/`"k"`. |
| `require` | `str` | `"and"` | Multi-method gate logic. Accepted values: `"and"` means every method in `tests` must pass; `"or"` means any method may pass. |
| `gate` | `str` | `"p"` | Significance gate. `"p"` uses raw p-values; `"fdr"`, `"q"`, `"q_value"`, `"q-value"`, `"fdr_bh"`, and `"bh"` use corrected q-values. |
| `alpha` | `float` | `0.05` | Significance cutoff for p/q gate decisions and matrix annotations. |
| `min_n` | `int` | `3` | Minimum complete paired observations before a pair is tested. Underpowered pairs remain in the long table with missing statistics. |
| `max_regressions` | `int` or `None` | `12` | Maximum selected pairs to send to regression plots. Use `0` to suppress regression plots or `None` to allow all selected pairs. |
| `regression_factor` | `str` or `None` | `None` | Grouping column used to color or split regression plots. `None` reuses the matrix grouping where appropriate. |
| `regression_test` | `str` | `"pearsonr"` | Correlation method annotated on regression plots. Accepts the same method names and aliases as `tests`. |
| `regression_combine` | `bool` | `True` | Overlay grouped regression fits in one panel where supported. |
| `normalize_x`, `normalize_y` | `bool`, tuple, `str`, or `None` | `False` | Optional normalization for regression axes. Accepted forms include `False`, `True` for min-max, explicit `(min, max)`, and `"Z-score"`. |
| `tick_label_size` | `int` or `float` | `20` | Tick-label size for saved matrix-style figures. |
| `value_matrices` | `str`, list-like, or `None` | `"p"` | Which p/q heatmap figures to save. Accepted values: `"p"`, `"q"`, `"both"`, `"none"`, or a list containing `"p"` and/or `"q"`. CSV matrices are still written for both p and q when `save=True`. |
| `plot_pvalue_matrices`, `plot_qvalue_matrices` | `bool` or `None` | `None` | Legacy boolean overrides for p/q heatmap saving. `None` follows `value_matrices`. |
| `plot_difference_matrices` | `bool` | `False` | Also compare correlation matrices between groups from `factor`/`split_by`. |
| `difference_comparisons` | list-like or `None` | `None` | Group comparisons for matrix differences, for example `["1-2"]` or explicit label pairs. `None` uses available planned/default comparisons. |
| `difference_gate` | `str` or `None` | `None` | Gate for matrix-difference outputs. `None` reuses `gate`; otherwise accepts the same p/q gate names. |
| `difference_alpha` | `float` or `None` | `None` | Significance cutoff for matrix differences. `None` reuses `alpha`. |
| `difference_test` | `str` | `"fisher_z"` | Statistical comparison for difference matrices. `"fisher_z"` compares independent Pearson correlations. |
| `plot_difference_signed`, `plot_difference_absolute`, `plot_difference_pvalue_matrices`, `plot_difference_qvalue_matrices`, `plot_difference_gate_matrix` | `bool` | mixed | Toggle signed difference, absolute difference, raw p-value, q-value, and gate-summary difference figures. Defaults are `True`, `True`, `True`, `False`, and `True`. |
| `run_label` | `str` or `None` | `None` | Run folder name. `None` builds a deterministic slug from columns and settings. |
| `if_exists` | `str` | `"overwrite"` | Run-folder collision policy. Accepted values: `"overwrite"`, `"version"`, `"error"`, or `"skip"`. |
| `save` | `bool` | `True` | Write run files. `False` computes and returns results without clearing or writing a run folder. |
| `write_manifest` | `bool` | `True` | Write `manifest.json` and update `_runs_index.csv` when saving. |
| `montage` | `bool` | `True` | Create `! Overview Montage.png` in the run folder when saving. |
| `group_col` / `condition_col` | `str` | `"Condition"` | Group column used when wrapping a raw `DataFrame`. `condition_col` is the legacy alias. |
| `group_cols` / `factor_cols` | list-like or `None` | `None` | Crossed grouping columns used when wrapping a raw `DataFrame`. |
| `subject_col` / `animal_col` | `str` | `"AnimalName"` | Subject/sample identifier column used by the raw `DataFrame` adapter. |
| `group_list`, `groups`, `conditions` | `groupList` or `None` | `None` | Optional group metadata for raw `DataFrame` input. `conditions` is the legacy name. |
| `dataframe_kwargs` | `dict` or `None` | `None` | Advanced options forwarded to the raw `DataFrame` adapter. |

## Returns

The function returns a dictionary. For a fresh run it contains the manifest keys
plus in-memory tables:

| Key | Type | Meaning |
|---|---|---|
| `run_label`, `fig_dir`, `data_dir` | `str` | Run name and output folders. Modern pipeline runs co-locate tables and figures, so `data_dir` is usually the same path as `fig_dir`. |
| `mode` | `str` | Square or rectangular matrix mode. |
| `n_rows`, `columns`, `against_columns` | mixed | Rows and column sets used after filtering. |
| `tests`, `require`, `gate`, `alpha`, `min_n` | mixed | Statistical settings recorded in the manifest. |
| `pairwise` | `pandas.DataFrame` | Long table of every tested pair and method, including `n`, correlation coefficient, p-value, and q-value where available. |
| `selected` | `pandas.DataFrame` | Subset of `pairwise` that passed the selected gate. |
| `n_pairs`, `n_selected`, `n_regressions` | `int` | Counts for tested pairs, selected pairs, and generated regression plots. |
| `groups` | `list[dict]` | Group-level summaries when grouped analysis is used. |
| `selected_pairs`, `plotted_pairs` | `list[dict]` | JSON-friendly summaries for selected and plotted pairs. |
| `value_matrices`, `plot_pvalue_matrices`, `plot_qvalue_matrices` | mixed | Saved matrix settings. |
| `difference_matrices` | `dict` | Difference-matrix summary, present even when disabled. |
| `specificity`, `conditions`, `n_conditions` | mixed | Row filter and merged filter-queue ledger when applicable. |
| `montage` | `str` | Path to the overview montage when one was written or reused. |
| `reused` | `bool` | True when `if_exists="skip"` returned an existing manifest. |

When `if_exists="skip"` reuses an existing run, the returned object is the cached
manifest. It may not include in-memory DataFrames such as `pairwise` and
`selected`.

## Saved Outputs

With `save=True`, files are written below:

```text
<fig_path>/Correlation Pipeline/<run_label>/
```

The run folder is both `fig_dir` and `data_dir`.

| Output | Meaning |
|---|---|
| `pairwise_correlations*.csv` | Long table of all tested pairs. |
| `selected_pairs*.csv` | Pairs that pass the selected `gate` and `require` rule. |
| `Matrices/coef_<Method>*.csv` | Correlation coefficient matrix for each method. |
| `Matrices/pvalues_<Method>*.csv` | Raw p-value matrix for each method. |
| `Matrices/qvalues_<Method>*.csv` | FDR q-value matrix for each method. |
| `Matrices/gate_matrix*.csv` | Boolean matrix of pairs passing the configured gate. |
| `Matrices/*Correlation Matrix*.svg` | Coefficient heatmaps. |
| `Matrices/*PValue Matrix*.svg` | Raw p-value heatmaps when enabled. |
| `Matrices/*FDR QValue Matrix*.svg` | Q-value heatmaps when enabled. |
| `Matrices/*Gate Passing Matrix*.svg` | Gate summary heatmap. |
| `Regressions/**/*.svg` | Optional regression figures for selected pairs. |
| `Matrix Differences/*` | Optional difference tables and matrix figures when `plot_difference_matrices=True`. |
| `manifest.json` | Stable run summary for reuse and reporting. |
| `../_runs_index.csv` | Append-only index of pipeline runs for this pipeline family. |
| `! Overview Montage.png` | Overview montage when `montage=True` and enough panels are captured. |

For a filter queue, each child group writes tagged filenames such as
`pairwise_correlations_Diagnosis.AD.csv` inside one shared run folder. The
combined manifest records a `conditions` list and queue-level totals.

## Examples

Run a p-gated all-vs-all matrix without writing files:

```python
from PyFLASH import correlation

result = correlation(
    batch,
    data_cols=["GFAP Mean", "IBA1 Mean", "CK1d Mean"],
    tests=("pearsonr", "spearmanr"),
    require="or",
    gate="p",
    max_regressions=0,
    save=False,
)
```

Run a grouped, saved analysis with p- and q-value heatmaps:

```python
result = correlation(
    batch,
    data_col_contains="Mean",
    factor="Diagnosis",
    gate="fdr",
    value_matrices="both",
    regression_factor="Diagnosis",
    run_label="diagnosis_marker_correlations",
)
```

Run two filtered conditions into one combined folder:

```python
result = correlation(
    batch,
    data_cols=["GFAP Mean", "IBA1 Mean", "CK1d Mean"],
    filter_by=[{"Diagnosis": "Control"}, {"Diagnosis": "AD"}],
    run_label="control_ad_correlations",
)
```

## Notes

- `gate="p"` is the default. Use `gate="fdr"` when the selected pairs should be
  based on multiple-testing-corrected q-values.
- P-value and q-value CSV matrices are saved even when their heatmap figures are
  disabled.
- `plot_difference_matrices=True` is for grouped correlation differences; it is
  separate from the main pairwise correlation selection.
- Pipeline outputs are designed to be reused through `manifest.json`, not by
  depending on private helper objects.

## See Also

- [adjusted_correlation](adjusted_correlation.md)
- [plot_regressions](plot_regressions.md)
- [plot_matrix_differences](plot_matrix_differences.md)
- [Pipeline manifests](../data-structures/pipeline-manifests.md)
- [Correlation statistics](../statistics/correlation.md)
- [Multiple testing](../statistics/multiple-testing.md)
- [Saving](../parameters/saving.md)
- [Filter By](../parameters/specificity.md)
- [API reference](../api-reference.md)
