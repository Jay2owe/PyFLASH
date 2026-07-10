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
| `data_cols`, `filtered_columns` | Marker/outcome columns to compare. If omitted, PyFLASH selects numeric summary columns. |
| `data_col_contains`, `data_col_regex`, `data_col_exclude` | Select marker columns by substring, regular expression, or exclusion text. |
| `by`, `factor`, `split_by` | Define groups. `by="conditions"` uses the group list. `factor` or `split_by` can name a summary-table column. |
| `filter_by`, `specificity`, `roi` | Restrict rows before analysis. `filter_by` is the preferred public name; `specificity` remains supported for older code. A filter queue writes one combined run folder with tagged files and a `conditions` ledger. |
| `comparisons` | Pairwise comparisons, for example `["1-2"]` or explicit group-label pairs. If omitted, PyFLASH resolves comparisons from groups/control. |
| `control` | Control group for fold change and effect-size direction. |
| `engine` | Test engine: `auto`, `mixed`, or `bootstrap`. `auto` selects the appropriate tested path. |
| `force_nonparametric` | Force non-parametric testing even if normality checks support parametric tests. |
| `posthoc` | Post-hoc test for multi-group non-parametric comparisons: `Conover` or `Dunn`. |
| `posthoc_correction` | Post-hoc correction: `auto`, `Bonferroni`, or `Uncorrected`. |
| `n_boot`, `random_state` | Bootstrap count and random seed for resampling paths. |
| `screen` | Add FDR q-values. P-values are always retained. Required when `gate="fdr"`. |
| `families` | FDR family definition, commonly `comparison`. |
| `gate` | Figure/significance gate: `p` or FDR/q-value aliases. |
| `alpha` | Significance cutoff. |
| `effect_ci`, `n_resamples` | Whether and how to compute bootstrap confidence intervals for effect sizes. |
| `report_power` | Include power-related columns where estimable. |
| `plot_volcano`, `plot_forest`, `plot_stats_matrix`, `plot_bars`, `plot_superplots` | Saved figure toggles. Tables are still returned/written when plots are disabled. |
| `max_bar_markers` | Maximum number of marker bar charts to save. |
| `min_n` | Minimum sample count per group before a marker/comparison is tested. |
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
| `../_runs_index.csv` | Append-only index of group-comparison runs. |
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
- [Multiple testing](../statistics/multiple-testing.md)
- [Saving](../parameters/saving.md)
- [Filter By](../parameters/specificity.md)
- [API reference](../api-reference.md)
