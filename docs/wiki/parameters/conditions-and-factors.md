# Groups And Factors

## Summary

Group and factor parameters control how rows are grouped after the input
table has been prepared. They do not choose metric columns and they do not
filter rows by themselves.

Use groups for the main experimental comparisons. Older PyFLASH code may call
the same objects conditions. Use factors or `split_by` to panel or compare by
columns such as `Diagnosis`, `Sex`, or `Time`.

## Used By

- Grouped plots such as [`plot_mean_bars`](../functions/plot_mean_bars.md),
  [`plot_regressions`](../functions/plot_regressions.md),
  [`plot_matrices`](../functions/plot_matrices.md),
  [`plot_radar`](../functions/plot_radar.md),
  [`plot_volcano`](../functions/plot_volcano.md), and distribution plots.
- Pipelines such as [`correlation`](../functions/correlation.md),
  [`adjusted_correlation`](../functions/adjusted_correlation.md),
  [`data_overview`](../functions/data_overview.md), and
  [`group_comparison`](../functions/group_comparison.md).
- Statistical annotation through `comparisons` and `multiple_comparison`.
- DataFrame input adaptation through `group_col`, `group_cols`, `groups`,
  `group_list`, and the legacy `conditions` name.

## Accepted Values

| Parameter | Meaning | Aliases |
|---|---|---|
| `groups` | Group order, labels, colors, styles, factors, and planned comparisons. | `group_list`; legacy `conditions` when it means a group list. |
| `group_col` | Column used while wrapping raw DataFrames into a primary PyFLASH group. | `condition_col`. |
| `group_cols` | Columns used while wrapping raw DataFrames into crossed groups. | `factor_cols`. |
| `by` | Chooses the broad grouping mode in functions that support pooled and group-panelled analysis. | None. |
| `factor` | Panels or compares by levels of a summary-table column or condition factor. | Some functions route `split_by=<column>` to `factor`. |
| `split_by` | Public grouping selector used by function pages and plot specs. | `factor` for column/factor splits; `by` for `"all"` or condition grouping in many functions. |
| `split_mode` | Controls how multi-key `split_by` values are expanded. | None. |
| `comparisons` | One-based group-index comparisons in the current group order. | Function-specific explicit pair forms may also be accepted. |
| `multiple_comparison` | Selects the shared multi-group statistics path for bar annotations. | None. |

### `by` options

| Option | Behavior |
|---|---|
| `"conditions"` | Analyze or panel by the resolved group list. |
| `"all"` | Pool rows into one analysis where the function supports pooled mode. |

### `split_by` options

| Option | Behavior |
|---|---|
| `"Condition"` | Use resolved PyFLASH groups. Aliases: `"conditions"`, `"groups"`. |
| `"all"` | Request pooled analysis in functions that map `split_by` to `by`. |
| Column or factor name | Use the levels of that column or condition factor. |
| List of names | In `data_overview`, split by several columns or factors. |

### `split_mode` options

| Option | Behavior |
|---|---|
| `"cross"` (default in `data_overview`) | Analyze populated combinations of all requested split keys. |
| `"parallel"` | Analyze each requested split key independently. |

### `multiple_comparison` options

| Option | Behavior |
|---|---|
| `"One-Way"` | Uses the one-way ANOVA path when the parametric multi-group path is allowed. |
| `"Two-Way"` | Uses the two-way ANOVA path in the shared bar-statistics engine. |

## Examples

Build groups explicitly:

```python
from PyFLASH import GroupBuilder
from PyFLASH.plotting import plot_mean_bars

groups = (
    GroupBuilder("Diagnosis")
    .add("Control", "Control", color="grey")
    .add("AD", "AD", color="red")
    .compare("Control", "AD")
    .build()
)

plot_mean_bars(
    df,
    data_cols=["GFAP_Count"],
    groups=groups,
    group_col="Diagnosis",
    subject_col="Subject",
    save=False,
)
```

Panel a pipeline by condition:

```python
from PyFLASH import correlation

result = correlation(
    batch,
    data_cols=["GFAP_Count", "Iba1_Count"],
    split_by="Condition",
    tests=("pearsonr",),
    save=False,
)
```

Use a multi-key overview split:

```python
from PyFLASH import data_overview

result = data_overview(
    batch,
    data_cols=["GFAP_Count", "Iba1_Count"],
    split_by=["Condition", "Sex"],
    split_mode="cross",
    effect_control="Control",
    save=False,
)
```

## Interactions

`group_col` is an input-adapter setting. `split_by` is an analysis grouping
setting. In a raw DataFrame call you often need both:

```python
plot_matrices(
    df,
    data_cols=["A", "B"],
    group_col="Diagnosis",
    subject_col="AnimalName",
    split_by="Diagnosis",
    save=False,
)
```

`split_by` conflicts with `factor` when it resolves to a factor. PyFLASH raises
instead of guessing if both provide different grouping instructions.

`comparisons` use the current condition or panel order. Condition lists can
store planned comparisons; if `comparisons=None`, the statistics engine uses
those planned comparisons when available, otherwise it builds default pairwise
comparisons for valid groups.

Crossed group lists carry component factors. Colors usually follow the
primary factor, while styles can distinguish the secondary factor in plots that
support condition styles.

## Common Errors

- Treating `split_by` as a row filter. Use `filter_by` to restrict
  rows.
- Passing `factor="Sex"` when the summary table has no `Sex` column and no
  condition factor named `Sex`.
- Supplying comparison strings for the wrong group order after changing
  condition order.
- Passing both `split_by` and `factor` with different values.
- Expecting every plot to support every `by` value. Some plots only support
  conditions and factors; pipelines commonly support `"all"` and
  `"conditions"`.

## See Also

- [Groups](../object-types/conditions.md)
- [Group specs](../data-structures/condition-specs.md)
- [Build groups workflow](../workflows/build-conditions.md)
- [Filter By and row filters](specificity.md)
- [Statistics options](statistics-options.md)
