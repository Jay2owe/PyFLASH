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

| Parameter | Meaning | Aliases |
|---|---|---|
| `comparisons` | Selects group contrasts in the current group order. | Some matrix-difference functions also accept explicit pair forms. |
| `force_nonparametric` | Controls whether the shared multi-group path may use parametric tests. | None. |
| `multiple_comparison` | Selects the shared multi-group comparison path for bar statistics. | None. |
| `posthoc` | Selects the ANOVA or Kruskal-Wallis post-hoc test. | ANOVA defaults to Tukey unless a parametric post-hoc is requested; Kruskal-Wallis uses the non-parametric choices. |
| `posthoc_correction` | Chooses how correctable post-hoc p-values are adjusted. | Applies to Dunn/Conover and Fisher LSD paths; boolean and common yes/no forms are normalized. |
| `ns` | Controls the text shown for non-significant annotations. | None. |
| `alpha` | Significance threshold for annotations, FDR rejection, gates, and matrices. | None. |
| `gate` | Chooses whether raw p-values or adjusted q-values define significance. | Strict screen-based gates usually accept only `"p"` and `"fdr"`; correlation-style gates also accept FDR aliases `q`, `qvalue`, `q_value`, `q-value`, `fdr_bh`, and `bh`. |
| `fdr_method` | Chooses the multiple-testing correction method. | Some helpers call this `method` in lower-level correction contexts. |
| `test` | Chooses the correlation method. | `tests` for multiple methods; `correlation` in plotting wrappers. |

### `force_nonparametric` options

| Option | Behavior |
|---|---|
| `False` (default in most callers) | Allows the shared statistics engine to use its normal parametric path when assumptions and sample sizes permit. |
| `True` | Forces the multi-group path to use non-parametric testing. The current two-group bar-statistics path still falls back to Mann-Whitney U only when a group is too small for the independent t-test path. |

### `multiple_comparison` options

| Option | Behavior |
|---|---|
| `"One-Way"` | Uses one-way ANOVA when the parametric multi-group path is allowed. |
| `"Two-Way"` | Uses the two-way ANOVA path in the shared bar-statistics engine. |

### `posthoc` options

| Option | Behavior |
|---|---|
| `"Tukey"` | Uses Tukey HSD after one-way ANOVA. This remains the default parametric path even though high-level callers default `posthoc` to `"Conover"` for the non-parametric path. |
| `"Dunnett"` | Uses Dunnett comparisons against one control group after one-way ANOVA. All comparison tokens must share one control, for example `["1-2", "1-3"]`. |
| `"Fisher LSD"` | Uses Fisher's least significant difference p-values after one-way ANOVA. |
| `"Bonferroni"`, `"Sidak"`, `"Holm-Sidak"` | Uses Fisher LSD p-values with the named selected-pair adjustment. |
| `"Scheffe"` | Uses Scheffe all-pairs comparisons after one-way ANOVA. |
| `"Tamhane T2"` | Uses Tamhane T2 all-pairs comparisons for unequal-variance-style post-hoc analysis. |
| `"Conover"` (default in current high-level callers) | Uses Conover post-hoc comparisons after Kruskal-Wallis. |
| `"Dunn"` | Uses Dunn post-hoc comparisons after Kruskal-Wallis. |
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

### `ns` options

| Option | Behavior |
|---|---|
| `"ns"` | Annotates non-significant comparisons as `ns`. |
| `"p"` | Prints a rounded p-value for non-significant comparisons. |

### `gate` options

| Option | Behavior |
|---|---|
| `"p"` (default in most callers) | Uses raw p-values for significance decisions. |
| `"fdr"` | Uses corrected q-values for significance decisions. Requires a workflow that computes q-values, often `screen=True`. |
| `"q"`, `"qvalue"`, `"q_value"`, `"q-value"`, `"fdr_bh"`, `"bh"` | Correlation-style FDR aliases accepted by the correlation gate helpers. They are not universal aliases for stricter screen-based pipelines such as `group_comparison`, `data_overview`, or `rhythm`. |

### `fdr_method` options

| Option | Behavior |
|---|---|
| `"fdr_bh"` (default in most FDR callers) | Benjamini-Hochberg FDR correction. |
| `"fdr_by"` | Benjamini-Yekutieli FDR correction. |
| `"holm"` | Holm family-wise correction. |
| `"bonferroni"` | Bonferroni family-wise correction. |
| `"sidak"` | Sidak family-wise correction. |

### `test` options

| Option | Behavior |
|---|---|
| `"pearsonr"` | Pearson linear correlation. Aliases: `"pearson"`, `"p"`. |
| `"spearmanr"` | Spearman rank correlation. Aliases: `"spearman"`, `"s"`. |
| `"kendalltau"` | Kendall rank correlation. Aliases: `"kendall"`, `"k"`. |

## GraphPad Prism Comparison

The shared one-way statistics path now covers the Prism-style post-hoc choices
most relevant to PyFLASH summary plots:

- Parametric ANOVA: Tukey, Dunnett, Fisher LSD, Bonferroni, Sidak,
  Holm-Sidak, Scheffe, and Tamhane T2.
- Non-parametric ANOVA/Kruskal-Wallis: Dunn, plus Conover, Nemenyi, and DSCF.
- Multiple-testing corrections: Bonferroni, Sidak, Holm, Holm-Sidak,
  Simes-Hochberg, Hommel, Benjamini-Hochberg FDR, Benjamini-Yekutieli FDR,
  and two-stage FDR variants.

Known Prism features that are not yet represented in this shared path are
repeated-measures ANOVA, three-way ANOVA, the Prism linear-trend post-test,
Newman-Keuls, and the full unequal-variance one-way ANOVA workflow
(Brown-Forsythe/Welch omnibus with Dunnett T3 or Games-Howell). `Tamhane T2`
is available as an unequal-variance-style post-hoc option, but the omnibus
selection is still PyFLASH's existing one-way ANOVA/Kruskal-Wallis decision.

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
an FDR gate because q-values are only computed during a screen. These
screen-based gates are strict about values: use `"p"` or `"fdr"`. Correlation
gate helpers are more permissive and also treat `"q"`, `"qvalue"`,
`"q_value"`, `"q-value"`, `"fdr_bh"`, and `"bh"` as FDR gates.

`comparisons=None` usually means "use planned comparisons from the condition
list when present; otherwise use default pairwise comparisons for the valid
groups."

## Common Errors

- Passing zero-based comparisons such as `"0-1"`. Comparison strings are
  one-based.
- Requesting `gate="fdr"` without enabling the screen that computes q-values.
- Supplying a parametric-only post-hoc such as `posthoc="Dunnett"` while also
  forcing the Kruskal-Wallis path. The Kruskal-Wallis post-hoc names are
  Conover, Dunn, Nemenyi, and DSCF.
- Treating `alpha` as a visual transparency option in statistical contexts.
  In these functions it is a significance threshold.
- Reusing comparison strings after changing group order.

## See Also

- [Group comparisons](../statistics/group-comparisons.md)
- [Multiple testing](../statistics/multiple-testing.md)
- [Correlation statistics](../statistics/correlation.md)
- [Groups and factors](conditions-and-factors.md)
- [Effect sizes](../statistics/effect-sizes.md)
