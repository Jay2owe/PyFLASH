# Statistics Options

## Summary

Statistics options control group-comparison tests, annotations, p-value
corrections, and significance gates. These options do not define the groups;
they act on the groups created by conditions, factors, `split_by`, and row
filters.

## Used By

- [`plot_mean_bars`](../functions/plot_mean_bars.md), through the shared
  `multipleComparisons` statistics engine.
- [`plot_volcano`](../functions/plot_volcano.md), group summary plots, and
  effect-size plots.
- [`group_comparison`](../functions/group_comparison.md) and the significance
  audit section of [`data_overview`](../functions/data_overview.md).
- [`correlation`](../functions/correlation.md) and
  [`adjusted_correlation`](../functions/adjusted_correlation.md), through
  correlation methods, gates, and `alpha`.
- [`rhythm`](../functions/rhythm.md), through parameter screens and FDR gates.
- Lower-level helpers in the statistics reference.

## Accepted Values

| Parameter | Accepted values | Behavior |
|---|---|---|
| `comparisons` | One-based strings such as `"1-2"`; some matrix-difference functions also accept explicit pairs. | Selects group contrasts in the current group order. |
| `force_nonparametric` | `True` or `False`. | Forces the shared multi-group path to use non-parametric testing. In the current two-group bar-statistics path, very small groups fall back to Mann-Whitney U, otherwise the independent t-test path is used. |
| `multiple_comparison` | Usually `"One-Way"` or `"Two-Way"`. | In the shared bar statistics path, `"One-Way"` selects one-way ANOVA when groups are normal; other values use the two-way ANOVA path. |
| `posthoc` | `"Conover"` or `"Dunn"`; common text variants such as `"Dunn's test"` normalize to `"Dunn"`. | Selects the Kruskal-Wallis post-hoc test. |
| `posthoc_correction` | `"auto"`, `"Bonferroni"`, `"Uncorrected"`, booleans, or common yes/no synonyms. | `"auto"` applies Bonferroni only when there are more than three comparisons. |
| `ns` | Usually `"ns"` or `"p"`. | Text for non-significant annotations. `"p"` prints a rounded p-value instead. |
| `alpha` | Float, commonly `0.05`. | Significance threshold for annotations, FDR rejection, gates, and matrices. |
| `gate` | Usually `"p"` or `"fdr"` in screening pipelines. Correlation-style gates also accept FDR aliases such as `"q"`, `"q_value"`, `"q-value"`, `"fdr_bh"`, and `"bh"`. | Chooses whether raw p-values or adjusted q-values define significance. |
| `fdr_method` / correction `method` | Any method accepted by `statsmodels.stats.multitest.multipletests`, such as `"fdr_bh"`, `"fdr_by"`, `"holm"`, `"bonferroni"`, or `"sidak"`. | Used by FDR and multiple-testing helpers. |
| `test` / `tests` / `correlation` | `"pearsonr"`, `"spearmanr"`, `"kendalltau"` and aliases `"pearson"`/`"p"`, `"spearman"`/`"s"`, `"kendall"`/`"k"`. | Correlation method selection. |

## Examples

Force non-parametric mean-bar tests:

```python
from PyFLASH.plotting import plot_mean_bars

plot_mean_bars(
    batch,
    data_cols=["GFAP_Count"],
    force_nonparametric=True,
    posthoc="Dunn",
    posthoc_correction="Bonferroni",
    comparisons=["1-2", "1-3", "2-3"],
)
```

Use an FDR gate in a correlation pipeline:

```python
from PyFLASH import correlation

result = correlation(
    batch,
    data_cols=["GFAP_Count", "Iba1_Count", "NeuN_Count"],
    tests=("pearsonr", "spearmanr"),
    gate="fdr",
    alpha=0.05,
)
```

Screen group comparisons with FDR:

```python
from PyFLASH import group_comparison

result = group_comparison(
    batch,
    data_cols=["GFAP_Count", "Iba1_Count"],
    control="Control",
    screen=True,
    gate="fdr",
    alpha=0.05,
)
```

## Interactions

The shared bar statistics engine first drops empty groups. If fewer than two
groups remain, no comparison is made.

For two valid groups, the current bar-statistics engine uses an independent
t-test when both groups have at least two observations. It falls back to
Mann-Whitney U only when a group is too small for the t-test path.

For three or more valid groups, the engine uses Kruskal-Wallis when normality
fails, when any group is too small, or when `force_nonparametric=True`. If the
normality path is allowed, `multiple_comparison="One-Way"` selects one-way
ANOVA; otherwise the two-way ANOVA path is used.

`gate="fdr"` requires an FDR table. In `group_comparison`, `data_overview`
significance audit, and `rhythm`, PyFLASH requires `screen=True` before using
an FDR gate because q-values are only computed during a screen.

`comparisons=None` usually means "use planned comparisons from the condition
list when present; otherwise use default pairwise comparisons for the valid
groups."

## Common Errors

- Passing zero-based comparisons such as `"0-1"`. Comparison strings are
  one-based.
- Requesting `gate="fdr"` without enabling the screen that computes q-values.
- Supplying `posthoc="Tukey"` for Kruskal-Wallis. The supported post-hoc names
  are Conover and Dunn.
- Treating `alpha` as a visual transparency option in statistical contexts.
  In these functions it is a significance threshold.
- Reusing comparison strings after changing group order.

## See Also

- [Group comparisons](../statistics/group-comparisons.md)
- [Multiple testing](../statistics/multiple-testing.md)
- [Correlation statistics](../statistics/correlation.md)
- [Groups and factors](conditions-and-factors.md)
- [Effect sizes](../statistics/effect-sizes.md)
