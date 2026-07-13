# group_comparison

## Summary

`group_comparison` runs per-marker comparisons between groups. It produces a
results table with p-values, optional q-values, effect sizes, confidence
intervals, power summaries, omnibus/descriptive tables, skipped-marker records,
summary figures, a manifest, and an overview montage.

Registry name: `group_comparison_pipeline`.

## Signature

```python
from PyFLASH import group_comparison

group_comparison(
    experiment,
    filtered_columns=None,
    data_cols=None,
    by="conditions",
    factor=None,
    split_by=None,
    specificity=None,
    filter_by=None,
    roi=None,
    comparisons=None,
    control=None,
    engine="auto",
    force_nonparametric=False,
    posthoc="Conover",
    posthoc_correction="auto",
    screen=False,
    families="comparison",
    gate="p",
    alpha=0.05,
    effect_ci=True,
    report_power=True,
    plot_volcano=True,
    plot_forest=True,
    plot_stats_matrix=True,
    plot_bars=True,
    plot_superplots=False,
    min_n=3,
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
| `data_cols` | list-like or `None` | `None` | Marker/outcome columns to compare. If omitted, PyFLASH selects usable numeric summary columns. Alias: `filtered_columns`. |
| `data_col_contains` | `str`, list-like, or `None` | `None` | Include marker columns containing these case-sensitive text fragments. Alias: `column_strings`. |
| `data_col_regex` | `str`, list-like, or `None` | `None` | Include marker columns matching one or more Python regular expressions. Alias: `regex_string`. |
| `data_col_exclude` | `str`, list-like, or `None` | `""` | Remove marker columns containing these text fragments. The empty-string default excludes nothing. Alias: `exclude`. |
| `by` | `str` | `"conditions"` | Grouping mode. `"conditions"` uses the group list; `"all"` pools rows where supported. |
| `split_by` | `str`, list-like, or `None` | `None` | Group by a summary-table column or condition factor such as `Diagnosis`. Alias: `factor`. |
| `filter_by` | mapping, tuple, list, or `None` | `None` | Restrict rows before analysis. A list of filters runs queue mode and tags outputs by filter value. Alias: `specificity`. |
| `roi` | `str`, list-like, or `None` | `None` | Restrict to one or more ROI bases. `None` uses the object's default summary. |
| `comparisons` | list-like or `None` | `None` | Pairwise comparisons, for example `["1-2"]` or explicit group-label pairs. `None` resolves comparisons from groups/control/default group order. |
| `control` | `str` or `None` | `None` | Control group for fold change and effect-size direction. `None` uses comparison/default logic. |
| `engine` | `str` | `"auto"` | Test engine. |
| `force_nonparametric` | `bool` | `False` | Force non-parametric testing even if normality checks support parametric tests. |
| `posthoc` | `str` | `"Conover"` | Post-hoc test for one-way ANOVA or Kruskal-Wallis paths. ANOVA accepts Tukey, Dunnett, Fisher LSD, Bonferroni, Sidak, Holm-Sidak, Scheffe, and Tamhane T2. Kruskal-Wallis accepts Conover, Dunn, Nemenyi, and DSCF. |
| `posthoc_correction` | `str` or `bool` | `"auto"` | Post-hoc correction for Dunn/Conover and Fisher LSD paths. |
| `n_boot` | `int` | `2000` | Bootstrap count for bootstrap engine paths. |
| `random_state` | `int` or `None` | `0` | Random seed for bootstrap/resampling paths. |
| `screen` | `bool` | `False` | Add FDR q-values. P-values are always retained. Required when `gate="fdr"`. |
| `families` | `str`, list-like, or mapping | `"comparison"` | FDR family definition. `"comparison"` corrects within each comparison; other family specifications can group tests by marker or global analysis needs. |
| `gate` | `str` | `"p"` | Figure/significance gate. |
| `alpha` | `float` | `0.05` | Significance cutoff for tests, gate counts, and figures. |
| `effect_ci` | `bool` | `True` | Compute bootstrap confidence intervals for effect sizes. |
| `n_resamples` | `int` | `5000` | Bootstrap resamples used for effect-size confidence intervals. |
| `report_power` | `bool` | `True` | Include power-related columns where estimable. |
| `plot_volcano`, `plot_forest`, `plot_stats_matrix`, `plot_bars` | `bool` | `True` | Saved figure toggles. Tables are still returned/written when plots are disabled. |
| `plot_superplots` | `bool` | `False` | Also save marker-level superplots. Disabled by default because this can create many files. |
| `max_bar_markers` | `int` | `30` | Maximum number of marker bar charts to save when `plot_bars=True`. |
| `tick_label_size` | `int` or `float` | `20` | Tick-label size for saved matrix-style figures. |
| `min_n` | `int` | `3` | Minimum sample count per group before a marker/comparison is tested. |
| `run_label` | `str` or `None` | `None` | Run folder name. `None` builds a deterministic slug from settings. |
| `if_exists` | `str` | `"overwrite"` | Run-folder collision policy. |
| `save` | `bool` | `True` | Write run files. `False` computes and returns results without clearing or writing a run folder. |
| `write_manifest` | `bool` | `True` | Write `manifest.json` and update `_runs_index.csv` when saving. |
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
| `"conditions"` (default) | Compare resolved groups. |
| `"all"` | Pool rows where the selected comparison path supports pooled mode. |

### `engine` options

| Option | Behavior |
|---|---|
| `"auto"` (default) | Selects the appropriate tested path. |
| `"mixed"` | Uses the mixed-model comparison path where supported. |
| `"bootstrap"` | Uses bootstrap/resampling paths where supported. |

### `posthoc` options

| Option | Behavior |
|---|---|
| `"Tukey"` | Uses Tukey HSD after one-way ANOVA. This remains the default parametric path even though this function's default `posthoc` value is `"Conover"` for non-parametric runs. |
| `"Dunnett"` | Uses Dunnett comparisons against one control group after one-way ANOVA. Comparison tokens must all share one control, for example `["1-2", "1-3"]`. |
| `"Fisher LSD"` | Uses Fisher's least significant difference p-values after one-way ANOVA. |
| `"Bonferroni"`, `"Sidak"`, `"Holm-Sidak"` | Uses Fisher LSD p-values with the named selected-pair adjustment. |
| `"Scheffe"` | Uses Scheffe all-pairs comparisons after one-way ANOVA. |
| `"Tamhane T2"` | Uses Tamhane T2 all-pairs comparisons for unequal-variance-style post-hoc analysis. |
| `"Conover"` (default) | Uses Conover post-hoc comparisons after Kruskal-Wallis. |
| `"Dunn"` | Uses Dunn post-hoc comparisons after Kruskal-Wallis. Common text variants normalize to this option. |
| `"Nemenyi"` | Uses Nemenyi rank-based all-pairs comparisons after Kruskal-Wallis. |
| `"DSCF"` | Uses Dwass-Steel-Critchlow-Fligner all-pairs comparisons after Kruskal-Wallis. |

### `posthoc_correction` options

| Option | Behavior |
|---|---|
| `"auto"` (default) | For Dunn/Conover, applies Bonferroni only when there are more than three comparisons. For explicit Fisher LSD, leaves p-values uncorrected. |
| `"Bonferroni"` | Applies Bonferroni correction. |
| `"Sidak"` | Applies Sidak correction. |
| `"Holm"` | Applies Holm correction. |
| `"Holm-Sidak"` | Applies Holm-Sidak correction. |
| `"Simes-Hochberg"` | Applies Simes-Hochberg correction. |
| `"Hommel"` | Applies Hommel correction. |
| `"FDR-BH"` | Applies Benjamini-Hochberg FDR correction. |
| `"FDR-BY"` | Applies Benjamini-Yekutieli FDR correction. |
| `"FDR-TSBH"` | Applies two-stage Benjamini-Hochberg FDR correction. |
| `"FDR-TSBKY"` | Applies two-stage Benjamini-Krieger-Yekutieli FDR correction. |
| `"Uncorrected"` | Leaves post-hoc p-values uncorrected. |
| Boolean or common yes/no synonym | Normalized to the matching corrected or uncorrected behavior. |

### `gate` options

| Option | Behavior |
|---|---|
| `"p"` (default) | Use raw p-values for figure/significance decisions. |
| `"fdr"` | Use corrected q-values. Requires `screen=True`. |

### `families` options

| Option | Behavior |
|---|---|
| `"comparison"` (default) | Corrects within each comparison. |
| List-like or mapping | Groups tests by marker, comparison, or another family structure needed for the analysis. |

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
| `pipeline` | `str` | Always `group_comparison`. |
| `run_label`, `fig_dir`, `data_dir` | `str` | Run name and output folders. Tables and figures are co-located in the run folder. |
| `n_markers`, `comparisons`, `groups` | mixed | Marker count and resolved group/comparison metadata. |
| `n_tests`, `n_significant`, `has_q` | mixed | Testing and multiple-testing summary. |
| `results_table` | `pandas.DataFrame` | Main per-marker comparison table, including p-values, q-values when screened, effects, and power fields where available. |
| `omnibus` | `pandas.DataFrame` | Omnibus test results for multi-group analyses. |
| `descriptives` | `pandas.DataFrame` | Group-level descriptive statistics used by the comparisons. |
| `skipped` | `pandas.DataFrame` | Markers/comparisons skipped because of constant values, missing data, or insufficient `min_n`. |
| `specificity`, `conditions`, `n_conditions` | mixed | Row filter and merged filter-queue ledger when applicable. |
| `montage` | `str` | Path to the overview montage when one was written or reused. |
| `reused` | `bool` | True when `if_exists="skip"` returned an existing manifest. |

When `if_exists="skip"` reuses an existing run, the returned object is the cached
manifest and may not include in-memory DataFrames.

When the `PyFLASH.report` collector is active, `group_comparison` also emits
structured report records with `kind="group_comparison"`. Those records
summarize the metric, tests, post-hoc comparisons, p-values, and group data;
they are report side effects, not extra keys in the returned dictionary.

## Saved Outputs

With `save=True`, files are written below:

```text
<fig_path>/Group Comparison Pipeline/<run_label>/
```

The run folder is both `fig_dir` and `data_dir`.

| Output | Meaning |
|---|---|
| `group_comparison_results*.csv` | Main per-marker comparison table. |
| `omnibus*.csv` | Omnibus test table. |
| `group_descriptives*.csv` | Group-level descriptive statistics. |
| `skipped_markers*.csv` | Markers skipped from one or more tests, when any exist. |
| `Volcano/Volcano <comparison> p*.svg` | Volcano plots using raw p-values. |
| `Volcano/Volcano <comparison> q*.svg` | Volcano plots using q-values when `screen=True`. |
| `Effect Size Forest p*.svg`, `Effect Size Forest q*.svg` | Effect-size forest figures. |
| `Stats Matrix p*.svg`, `Stats Matrix q*.svg` | Group-by-marker significance matrix figures. |
| `SuperPlots/SuperPlot <marker>*.svg` | Optional superplots when `plot_superplots=True`. |
| Bar-chart SVGs | Optional marker bar charts from the mean-bar plotting layer. |
| `manifest.json` | Stable run summary for reuse and reporting. |
| `../_runs_index.csv` | One-row-per-run index for group-comparison runs; reruns with the same run label replace the matching index row. |
| `! Overview Montage.png` | Overview montage when `montage=True`. |

For a filter queue, child files receive tags such as
`_Diagnosis.AD`, and the combined manifest records each condition in a
`conditions` list.

## Examples

Compare all condition groups for selected markers without saving:

```python
from PyFLASH import group_comparison

result = group_comparison(
    batch,
    data_cols=["GFAP Mean", "IBA1 Mean", "CK1d Mean"],
    by="conditions",
    comparisons=["1-2"],
    save=False,
)

print(result["results_table"].head())
print(result["skipped"].head())
```

Run a saved, FDR-screened comparison:

```python
result = group_comparison(
    batch,
    data_col_contains="Mean",
    factor="Diagnosis",
    control="Control",
    screen=True,
    gate="fdr",
    run_label="diagnosis_marker_comparison",
)
```

## Notes

- `screen=True` adds q-values; it does not remove p-values.
- `gate="fdr"` requires `screen=True` because q-values must exist before figures
  and manifest counts can use an FDR gate.
- A skipped marker table is part of the output contract when markers are not
  testable. Use it before interpreting missing rows in `results_table`.
- The pipeline records tested outputs in `manifest.json`; avoid depending on
  private engine-specific objects.

## See Also

- [data_overview](data_overview.md)
- [linear_model](linear_model.md)
- [plot_volcano](plot_volcano.md)
- [plot_effect_forest](plot_effect_forest.md)
- [plot_group_matrix](plot_group_matrix.md)
- [plot_superplot](plot_superplot.md)
- [Pipeline manifests](../data-structures/pipeline-manifests.md)
- [Group comparison statistics](../statistics/group-comparisons.md)
- [Effect sizes](../statistics/effect-sizes.md)
- [Power](../statistics/power.md)
- [Multiple testing](../statistics/multiple-testing.md)
- [Saving](../parameters/saving.md)
- [Filter By](../parameters/specificity.md)
- [API reference](../api-reference.md)
