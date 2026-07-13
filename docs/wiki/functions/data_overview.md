# data_overview

## Summary

`data_overview` creates a descriptive and quality-control run for a summary
table. It can classify columns, count groups, summarize numeric markers, test
normality, flag outliers, detect high covariation, summarize condition
distributions, estimate effect sizes, audit significance results, generate a
dataset-health scorecard, estimate power/readiness, save figures and tables, and
write a run manifest.

Registry name: `data_overview_pipeline`.

## Signature

```python
from PyFLASH import data_overview

data_overview(
    experiment,
    filtered_columns=None,
    data_cols=None,
    by="all",
    factor=None,
    split_by=None,
    split_mode="cross",
    nest=False,
    specificity=None,
    filter_by=None,
    save=True,
    include_inventory=True,
    include_group_counts=True,
    include_descriptives=True,
    include_normality=True,
    include_outliers=True,
    include_covariation=True,
    include_condition_distributions=True,
    include_effect_sizes=True,
    include_significance_audit=True,
    include_scorecard=True,
    include_readiness=True,
    screen=False,
    gate="p",
    alpha=0.05,
    min_n=3,
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
| `pandas.DataFrame` | Yes | Wrapped internally. Provide `group_col`, `group_cols`, `subject_col`, or `dataframe_kwargs` when the table does not already carry PyFLASH metadata. |

## Parameters

| Parameter | Type | Default | Meaning |
|---|---|---:|---|
| `experiment` | `Batch`, `Experiment`, `MiniExperiment`, or wrapped `DataFrame` | required | Data source containing a summary table. |
| `data_cols` | list-like or `None` | `None` | Numeric columns to include. If omitted, PyFLASH selects usable numeric summary columns. Alias: `filtered_columns`. |
| `data_col_contains` | `str`, list-like, or `None` | `None` | Include columns containing these case-sensitive text fragments. Alias: `column_strings`. |
| `data_col_regex` | `str`, list-like, or `None` | `None` | Include columns matching one or more Python regular expressions. Alias: `regex_string`. |
| `data_col_exclude` | `str`, list-like, or `None` | `""` | Remove columns containing these text fragments. The empty-string default excludes nothing. Alias: `exclude`. |
| `by` | `str` | `"all"` | Overview grouping mode. |
| `split_by` | `str`, list-like, or `None` | `None` | Group by one or more summary-table columns or condition factors. Can be a list. Alias: `factor`. |
| `split_mode` | `str` | `"cross"` | Multi-key `split_by` behavior. |
| `nest` | `bool` | `False` | Nested grouping mode for compatible grouped summaries. |
| `filter_by` | mapping, tuple, list, or `None` | `None` | Restrict rows before analysis. A list of filters runs queue mode and tags outputs by filter value. Alias: `specificity`. |
| `roi` | `str`, list-like, or `None` | `None` | Restrict to one or more ROI bases. `None` uses the object's default summary. |
| `include_inventory` | `bool` | `True` | Build `column_inventory` with role, missingness, sentinel counts, and availability. |
| `include_group_counts` | `bool` | `True` | Build group/sample count summaries. |
| `include_descriptives` | `bool` | `True` | Build numeric descriptive statistics by group. |
| `include_normality` | `bool` | `True` | Run normality summaries for numeric columns. |
| `include_outliers` | `bool` | `True` | Flag outlying values and affected subjects. |
| `include_covariation` | `bool` | `True` | Find highly correlated numeric column pairs. |
| `include_condition_distributions` | `bool` | `True` | Summarize per-condition or per-factor distributions. |
| `include_effect_sizes` | `bool` | `True` | Compute control-vs-group effect sizes. |
| `include_significance_audit` | `bool` | `True` | Run the statistical audit. Disable this for a faster descriptive-only overview. |
| `include_scorecard` | `bool` | `True` | Build the dataset-health scorecard and narrative. |
| `include_readiness` | `bool` | `True` | Estimate marker readiness and minimum detectable effect. |
| `audit_comparisons` | list-like or `None` | `None` | Significance-audit contrasts, for example `["1-2"]` or explicit label pairs. `None` uses planned/default comparisons. |
| `audit_control` | `str` or `None` | `None` | Control group for audit contrasts. `None` uses the resolved comparison/default logic. |
| `audit_axis` | `str` | `"split"` | Transition axis for significance-audit summaries. |
| `screen` | `bool` | `False` | Add FDR q-values to audit/group-testing outputs. Required when `gate="fdr"`. |
| `gate` | `str` | `"p"` | Audit/significance gate. |
| `run_both` | `bool` | `True` | In the audit, run companion parametric/non-parametric tests where supported so concordance can be assessed. |
| `outlier_methods` | tuple/list of `str` or `str` | `("rout",)` | Outlier methods to run. Combine values with a tuple/list. |
| `iqr_k` | `float` | `1.5` | Interquartile-range multiplier used when `outlier_methods` includes `"iqr"`. |
| `mad_threshold` | `float` | `3.5` | Modified z-score threshold used when `outlier_methods` includes `"mad"`. |
| `rout_q` | `float` | `1.0` | ROUT false-discovery percentage used when `outlier_methods` includes `"rout"`. |
| `covariation_method` | `str` | `"pearsonr"` | Correlation method for high-covariation detection. |
| `covariation_threshold` | `float` | `0.9` | Absolute correlation threshold for high-covariation detection. |
| `min_n` | `int` | `3` | Minimum rows needed for statistical summaries. |
| `alpha` | `float` | `0.05` | Significance cutoff for audit and plotting annotations. |
| `plot_missingness`, `plot_covariation`, `plot_group_counts`, `plot_availability`, `plot_descriptives`, `plot_normality`, `plot_outliers` | `bool` | `True` | Saved-figure toggles for the corresponding overview sections. Tables still compute when the matching `include_*` flag is enabled. |
| `plot_covariation_pairs`, `plot_condition_distributions`, `plot_condition_distribution_zscores`, `plot_condition_fingerprint`, `plot_condition_variability` | `bool` | `True` | Saved-figure toggles for covariation and condition-distribution sections. |
| `plot_effect_sizes`, `plot_significance_audit`, `plot_scorecard`, `plot_readiness` | `bool` | `True` | Saved-figure toggles for effect-size, audit, scorecard, and readiness sections. |
| `scorecard_thresholds` | mapping or `None` | `None` | Override dataset-health grade thresholds such as imbalance or missingness cutoffs. `None` uses built-in thresholds. |
| `power` | `float` | `0.8` | Target statistical power for readiness summaries. |
| `mde_threshold` | `float` | `0.8` | Effect-size threshold for marker-readiness summaries. |
| `condition_distribution_plot` | `str` | `"raincloud"` | Figure style for condition distributions. |
| `fingerprint_stat` | `str` | `"median"` | Statistic used in condition fingerprint heatmaps. |
| `variability_stat` | `str` | `"cv_pct"` | Statistic used in condition variability heatmaps. |
| `effect_control` | `str` or `None` | `None` | Control group for effect-size comparisons. `None` uses the first resolved group. |
| `max_plot_items` | `int` | `30` | Limits very large overview figures. |
| `tick_label_size` | `int` or `float` | `20` | Tick-label size for saved overview figures. |
| `run_label` | `str` or `None` | `None` | Run folder name. `None` builds a deterministic slug from settings. |
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

### `by` options

| Option | Behavior |
|---|---|
| `"all"` (default) | Pool rows for overview summaries. |
| `"conditions"` | Use the resolved group list for grouped overview summaries. |

### `split_mode` options

| Option | Behavior |
|---|---|
| `"cross"` (default) | Analyze populated combinations of all requested `split_by` keys. |
| `"parallel"` | Analyze each requested `split_by` key independently. |

### `audit_axis` options

| Option | Behavior |
|---|---|
| `"split"` (default) | Summarize significance-audit transitions by split/group context. |
| `"fdr"` | Summarize transitions around FDR screening. |
| `"exclusions"` | Summarize transitions around exclusion handling. |

### `gate` options

| Option | Behavior |
|---|---|
| `"p"` (default) | Use raw p-values for audit/significance decisions. |
| `"fdr"` | Use corrected q-values. Requires `screen=True`. |

### `outlier_methods` options

| Option | Behavior |
|---|---|
| `"rout"` (default) | Use ROUT outlier detection with `rout_q`. |
| `"iqr"` | Use interquartile-range outlier detection with `iqr_k`. |
| `"mad"` | Use modified-z-score outlier detection with `mad_threshold`. |

### `covariation_method` options

| Option | Behavior |
|---|---|
| `"pearsonr"` (default) | Pearson linear correlation. Aliases: `"pearson"`, `"p"`. |
| `"spearmanr"` | Spearman rank correlation. Aliases: `"spearman"`, `"s"`. |
| `"kendalltau"` | Kendall rank correlation. Aliases: `"kendall"`, `"k"`. |

### `condition_distribution_plot` options

| Option | Behavior |
|---|---|
| `"raincloud"` (default) | Draw raincloud-style condition distributions. |
| `"boxstrip"` | Draw box plots with overlaid strip points. |
| `"violin"` | Draw violin plots. |
| `"strip"` | Draw strip plots. |

### `fingerprint_stat` options

| Option | Behavior |
|---|---|
| `"median"` (default) | Use medians in condition fingerprint heatmaps. |
| `"mean"` | Use means in condition fingerprint heatmaps. |
| Other supported numeric summary statistic | Use that statistic if the overview path can compute it. |

### `variability_stat` options

| Option | Behavior |
|---|---|
| `"cv_pct"` (default) | Use percent coefficient of variation. |
| `"sd"` | Use standard deviation. |
| `"iqr"` | Use interquartile range. |
| Other column from `condition_distribution_stats.csv` | Use that saved distribution-statistic column. |

### `if_exists` options

| Option | Behavior |
|---|---|
| `"overwrite"` (default) | Clear the existing generated run folder, then recompute. |
| `"version"` | Keep the old run and write to the next free suffix such as `_v2`. |
| `"error"` | Raise if the run folder already exists. |
| `"skip"` | Reuse the cached manifest when available instead of recomputing. |

## Returns

The function returns a dictionary. For a fresh run it contains manifest keys plus
the computed tables:

| Key | Type | Meaning |
|---|---|---|
| `pipeline` | `str` | Always `data_overview`. |
| `run_label`, `fig_dir`, `data_dir` | `str` | Run name and output folders. Tables and figures are co-located in the run folder. |
| `n_rows`, `n_numeric_columns`, `groups` | mixed | Dataset and grouping summary after filtering. |
| `column_inventory` | `pandas.DataFrame` | Column roles, missing values, sentinel values, and availability. |
| `inventory_counts` | `dict` | Count of columns by role. |
| `group_counts` | `pandas.DataFrame` | Grouping axes and animal/subject counts. |
| `availability_by_condition` | `pandas.DataFrame` | Per-condition availability summary when generated. |
| `descriptives` | `pandas.DataFrame` | Numeric summary statistics by group. |
| `normality` | `pandas.DataFrame` | Normality screen results. |
| `outliers` | `pandas.DataFrame` | Outlier flags by animal/subject, group, and column. |
| `outlier_animals` | `pandas.DataFrame` | Animals/subjects with one or more outlier flags. |
| `covariation` | `pandas.DataFrame` | High-covariation pair table. |
| `covariation_matrix` | `pandas.DataFrame` | Correlation matrix for selected numeric columns. |
| `condition_distributions` | `pandas.DataFrame` | Group/condition distribution statistics. |
| `condition_fingerprint`, `condition_variability` | `pandas.DataFrame` | Group-by-marker heatmap source tables. |
| `effect_sizes` | `pandas.DataFrame` | Control-vs-group effect sizes. |
| `significance_audit` | `pandas.DataFrame` | Audit tests, p-values, q-values when screened, effect summaries, and concordance flags. |
| `significance_audit_transitions` | `pandas.DataFrame` | Gained/lost/significant/not-significant audit transition table when requested. |
| `scorecard` | `pandas.DataFrame` | Dataset-health grades and threshold rules. |
| `dataset_health_narrative` | `str` | Grounded summary of the scorecard. |
| `mde_by_marker` | `pandas.DataFrame` | Minimum detectable effect estimates. |
| `marker_readiness` | `pandas.DataFrame` | Readiness verdicts and suggested transforms. |
| `provenance` | `dict` | Package versions, source hash where available, and resolved parameters. |
| `sig_audit_bundle` | `str` or `None` | Path to the assembled significance-audit bundle when produced. |
| `specificity`, `conditions`, `n_conditions` | mixed | Row filter and merged filter-queue ledger when applicable. |
| `montage` | `str` | Path to the overview montage when one was written or reused. |
| `reused` | `bool` | True when `if_exists="skip"` returned an existing manifest. |

Disabled sections return empty DataFrames or omit section-specific files, rather
than inventing values.

When `if_exists="skip"` reuses an existing run, the returned object is the cached
manifest and may not contain in-memory DataFrames.

When the `PyFLASH.report` collector is active, `data_overview` also emits
structured report records. These are report side effects, not keys in the
returned dictionary. Depending on enabled sections, record kinds can include
`audit_transitions`, `power_mde`, `marker_readiness`, and `dataset_health`.

## Saved Outputs

With `save=True`, files are written below:

```text
<fig_path>/Data Overview Pipeline/<run_label>/
```

The run folder is both `fig_dir` and `data_dir`.

| Output | Meaning |
|---|---|
| `column_inventory*.csv` | Column role and availability table. |
| `group_counts*.csv` | Group/sample counts. |
| `availability_by_condition*.csv` | Availability by group/condition when generated. |
| `descriptive_stats*.csv` | Numeric descriptive statistics. |
| `normality*.csv` | Normality results. |
| `outliers*.csv`, `outlier_animals*.csv` | Value-level and animal/subject-level outlier summaries. |
| `covariation_pairs*.csv`, `covariation_matrix*.csv` | High-covariation pair list and matrix. |
| `condition_distribution_stats*.csv` | Condition/factor distribution summaries. |
| `condition_fingerprint*.csv`, `condition_variability*.csv` | Heatmap source tables. |
| `effect_sizes*.csv` | Control-vs-group effect-size table. |
| `significance_audit*.csv` | Statistical audit table. |
| `significance_audit_transitions*.csv` | Audit transition table when generated. |
| `scorecard*.csv` | Dataset-health scorecard. |
| `mde_by_marker*.csv`, `marker_readiness*.csv` | Power/readiness summaries. |
| `provenance.json` | Package, source, and parameter provenance. |
| `sig_audit/` | Reproducibility bundle for the significance audit when assembled. |
| `*.svg` | Overview figures such as missingness, group counts, descriptives, normality, outliers, covariation, condition distributions, effect sizes, audit, scorecard, MDE, and readiness plots. |
| `manifest.json` | Stable run summary for reuse and reporting. |
| `../_runs_index.csv` | One-row-per-run index for data-overview runs; reruns with the same run label replace the matching index row. |
| `! Overview Montage.png` | Overview montage when `montage=True`. |

For a filter queue, child files receive tags such as
`_Diagnosis.Control`, and the combined manifest records each condition in a
`conditions` list.

## Examples

Fast, in-memory overview of selected markers:

```python
from PyFLASH import data_overview

result = data_overview(
    batch,
    data_cols=["GFAP Mean", "IBA1 Mean", "CK1d Mean"],
    by="conditions",
    include_significance_audit=False,
    include_scorecard=False,
    include_readiness=False,
    save=False,
)

print(result["column_inventory"].head())
print(result["inventory_counts"])
```

Saved condition overview with audit and readiness:

```python
result = data_overview(
    batch,
    data_col_contains="Mean",
    split_by="Condition",
    screen=True,
    gate="fdr",
    run_label="condition_overview",
)
```

Cross two grouping columns:

```python
result = data_overview(
    batch,
    data_cols=["GFAP Mean", "IBA1 Mean"],
    split_by=["Condition", "Sex"],
    split_mode="cross",
    effect_control="WT",
    save=False,
)
```

## Notes

- `include_*` flags control computation and tables. `plot_*` flags only control
  saved figures for computed sections.
- `gate="fdr"` requires `screen=True` for significance-audit workflows because
  q-values are created by screening.
- Sentinels such as `NOT_INCLUDED_IN_EXPERIMENT` are counted separately from
  true missing values in the inventory.
- The scorecard and readiness sections are descriptive aids. They should guide
  review, not replace study-specific statistical decisions.

## See Also

- [group_comparison](group_comparison.md)
- [Pipeline manifests](../data-structures/pipeline-manifests.md)
- [Summary table](../data-structures/summary-table.md)
- [Group comparison statistics](../statistics/group-comparisons.md)
- [Effect sizes](../statistics/effect-sizes.md)
- [Power](../statistics/power.md)
- [Saving](../parameters/saving.md)
- [Filter By](../parameters/specificity.md)
- [API reference](../api-reference.md)
