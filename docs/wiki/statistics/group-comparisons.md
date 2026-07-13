# Group Comparisons

## Summary

PyFLASH group comparisons test whether numeric measurements differ between
groups. The core comparison helper is used by bar plots and by the
[group_comparison](../functions/group_comparison.md) pipeline. The pipeline adds
marker-by-marker tables, optional screening corrections, effect sizes, power
columns, and saved figures.

## Where PyFLASH Uses It

- [plot_mean_bars](../functions/plot_mean_bars.md) uses the shared comparison
  helper when drawing significance annotations and writing statistics tables.
- [group_comparison](../functions/group_comparison.md) runs planned comparisons
  across markers and can use `auto`, `mixed`, or `bootstrap` engines.
- [plot_group_matrix](../functions/plot_group_matrix.md) displays group-effect
  summaries from comparison-style outputs.
- [plot_effect_forest](../functions/plot_effect_forest.md) can compute and
  display descriptive Hedges g summaries directly from grouped data.
- Structured report records can summarize the selected test, group
  descriptives, p-values, pairwise rows, and effect-size text.

## Inputs

Typical inputs are numeric measurement columns, a grouping column, and optional
comparison labels. Plot-level functions may receive `groupList`; pipeline runs
usually use `group_col`, `control`, `comparisons`, `factor`, and row filters.

The shared comparison helper drops non-numeric and missing values before testing.
Each non-empty group is counted after this filtering. When comparisons are not
provided, PyFLASH uses all pairwise group combinations.

The `group_comparison` pipeline can run:

- `auto`: marker-wise group comparisons using the shared helper.
- `mixed`: ROI-level mixed modelling where ROI rows and nesting information are
  available.
- `bootstrap`: ROI-level bootstrap summaries where ROI rows are available.

If ROI-level inputs are not available or a nested model cannot be fitted, the
pipeline falls back to the `auto` engine for that marker and records the engine
used in the output.

## Outputs

Common output columns include:

- `marker`, `comparison`, `reference`, and `group`.
- `test` and `engine`, describing the method used.
- `n_reference`, `n_group`, `mean_reference`, and `mean_group`.
- `percent_change`, effect-size columns, and confidence interval columns.
- `p`, optional `q`, and `significant`.
- `omnibus_p`, `icc`, `achieved_power`, and `required_n_80` where available.

The pipeline also writes descriptives, skipped-marker tables, omnibus summaries,
figures, and a `manifest.json` file in its run folder.

## Interpretation

For two groups, the shared helper uses an independent two-sample t-test when
both groups have enough values. If a group is too small for that route, it uses a
Mann-Whitney U test. For three or more groups, PyFLASH checks distributional
support and chooses between one-way ANOVA with Tukey post-hoc comparisons or
Kruskal-Wallis with Conover/Dunn-style post-hoc comparisons.

The normality check pools group values and combines several tests when enough
data are available. It is a routing aid for multi-group comparisons, not a proof
that assumptions are fully satisfied.

Read a significant comparison as evidence that the tested groups differ for the
specified marker under the selected method and filtering. Read it alongside the
effect size, confidence interval, sample sizes, skipped rows, and correction
family.

## Limitations

The automatic route does not establish causality and does not replace a planned
statistical design. Small groups, zero variance, many missing values, repeated
measurements treated as independent, and post-hoc selection can make p-values
and effect sizes unstable.

For multi-group `auto` comparisons in the pipeline, PyFLASH uses one-way
comparison logic. Use the linear-model tools when covariates, categorical
terms, interactions, or adjusted means are the primary question.

## See Also

- [Effect Sizes](effect-sizes.md)
- [Multiple Testing](multiple-testing.md)
- [Power](power.md)
- [group_comparison](../functions/group_comparison.md)
- [plot_mean_bars](../functions/plot_mean_bars.md)
