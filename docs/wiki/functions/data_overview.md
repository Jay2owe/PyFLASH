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

Only the public arguments are shown. Internal underscore-prefixed queue arguments
are reserved for PyFLASH.

## Input Object Types

| Object type | Accepted? | Notes |
|---|---:|---|
| `Batch` | Yes | Main input for saved PyFLASH analyses. |
| `Experiment` / `MiniExperiment` | Yes | Works when a summary table and output paths are available. |
| `pandas.DataFrame` | Yes | Wrapped internally. Provide `group_col`, `group_cols`, `subject_col`, or `dataframe_kwargs` when the table does not already carry PyFLASH metadata. |

## Parameters

| Parameter | Meaning |
|---|---|
| `data_cols`, `filtered_columns` | Numeric columns to include. If omitted, PyFLASH selects usable numeric summary columns. |
| `data_col_contains`, `data_col_regex`, `data_col_exclude` | Select columns by substring, regular expression, or exclusion text. Legacy aliases are `column_strings`, `regex_string`, and `exclude`. |
| `by`, `factor`, `split_by` | Define overview groups. `by="all"` pools rows. `by="conditions"` uses the group list. `factor` or `split_by` names one or more grouping columns. |
| `split_mode` | For multiple `split_by` keys, `cross` analyzes populated combinations and `parallel` analyzes each axis independently. |
| `nest` | Nested grouping mode for compatible grouped summaries. |
| `filter_by`, `specificity`, `roi` | Restrict rows before analysis. `filter_by` is the preferred public name; `specificity` remains supported for older code. A filter queue writes one combined run folder with tagged files and a `conditions` ledger. |
| `include_inventory` | Build `column_inventory` with role, missingness, sentinel counts, and availability. |
| `include_group_counts` | Build group/sample count summaries. |
| `include_descriptives` | Build numeric descriptive statistics by group. |
| `include_normality` | Run normality summaries for numeric columns. |
| `include_outliers` | Flag outlying values and affected subjects. |
| `include_covariation` | Find highly correlated numeric column pairs. |
| `include_condition_distributions` | Summarize per-condition or per-factor distributions. |
| `include_effect_sizes` | Compute control-vs-group effect sizes. |
| `include_significance_audit` | Run the statistical audit. This is on by default. |
| `include_scorecard` | Build the dataset-health scorecard and narrative. |
| `include_readiness` | Estimate marker readiness and minimum detectable effect. |
| `audit_comparisons`, `audit_control`, `audit_axis` | Configure significance-audit contrasts and transition axes. `audit_axis` accepts modes such as `split`, `fdr`, and `exclusions`. |
| `screen` | Add FDR q-values to audit/group-testing outputs. Required when `gate="fdr"`. |
| `gate` | Audit/significance gate: `p` or FDR/q-value aliases. |
| `run_both` | In the audit, run companion parametric/non-parametric tests where supported so concordance can be assessed. |
| `outlier_methods` | Outlier methods: `rout`, `iqr`, `mad`, or a tuple combining them. |
| `iqr_k`, `mad_threshold`, `rout_q` | Thresholds for the outlier methods. |
| `covariation_method`, `covariation_threshold` | Correlation method and absolute threshold for high-covariation detection. |
| `min_n` | Minimum rows needed for statistical summaries. |
| `alpha` | Significance cutoff for audit and plotting annotations. |
| `plot_*` flags | Control saved figures independently from table computation. For example, `plot_significance_audit=False` suppresses the SVG but still allows `significance_audit.csv` when the section is included. |
| `scorecard_thresholds` | Override dataset-health grade thresholds such as imbalance or missingness cutoffs. |
| `power`, `mde_threshold` | Power target and effect-size threshold for readiness summaries. |
| `condition_distribution_plot` | Figure style for condition distributions: `raincloud`, `boxstrip`, `violin`, or `strip`. |
| `fingerprint_stat`, `variability_stat` | Statistics used in condition fingerprint and variability heatmaps. |
| `effect_control` | Control group for effect-size comparisons. Defaults to the first resolved group. |
| `max_plot_items` | Limits very large overview figures. |
| `run_label` | Run folder name. If omitted, PyFLASH builds a deterministic slug from settings. |
| `if_exists` | Run-folder collision policy: `overwrite`, `version`, `error`, or `skip`. |
| `save` | If true, write run files. |
| `write_manifest` | Write `manifest.json` and update `_runs_index.csv` when saving. |
| `montage` | If true and saving, create `! Overview Montage.png`. |

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
| `../_runs_index.csv` | Append-only index of data-overview runs. |
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
