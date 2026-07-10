# Effect Sizes

## Summary

Effect sizes estimate the magnitude and direction of a difference or
association. PyFLASH reports them next to p-values in group comparisons and some
summary plots so that a result can be interpreted as more than significant or
not significant.

## Where PyFLASH Uses It

- [group_comparison](../functions/group_comparison.md) writes Hedges g,
  rank-biserial correlation, confidence intervals, and interpretation labels
  where applicable.
- [plot_mean_bars](../functions/plot_mean_bars.md) can include effect-size text
  in statistics outputs when effect sizes are enabled.
- [plot_effect_forest](../functions/plot_effect_forest.md) visualizes group
  effect estimates.
- [plot_group_matrix](../functions/plot_group_matrix.md) visualizes group-wise
  effect patterns.
- [data_overview](../functions/data_overview.md) uses detectable-effect
  calculations when estimating power and measurement sensitivity.

## Inputs

Effect-size functions use the same cleaned numeric samples as the corresponding
test. For pairwise group comparisons, direction is computed from the ordered
comparison: the group value is contrasted against the reference value. In
pipeline tables, `reference` and `group` show the direction that was used.

Bootstrap confidence intervals require enough independent sample values to
resample. If the interval cannot be estimated reliably, PyFLASH leaves the
interval as missing rather than inventing a bound.

## Outputs

PyFLASH can report:

- `cohen_d`: standardized mean difference for two groups (computed by the `cohens_d()` helper).
- `hedges_g`: small-sample corrected standardized mean difference.
- `rank_biserial`: nonparametric pairwise effect size for rank-based tests.
- `eta_squared` and `omega_squared`: ANOVA-style omnibus effect sizes.
- `epsilon_squared`: Kruskal-Wallis omnibus effect size.
- `ci_low` and `ci_high`: bootstrap confidence interval bounds where available.
- `interpretation`: a magnitude label such as negligible, small, medium, or
  large.

Magnitude labels use conventional numeric bands. For standardized differences
and correlations, values below 0.2 are negligible, below 0.5 are small, below
0.8 are medium, and 0.8 or above is large. For omnibus variance-style effects,
values below 0.06 are small, below 0.14 are medium, and 0.14 or above is large.

## Interpretation

The sign describes direction; the absolute value describes magnitude. For
planned pairwise comparisons, a positive Hedges g means the named group is
higher than the reference group after PyFLASH's filtering and aggregation. A
negative value means it is lower.

Effect sizes should be interpreted with the confidence interval, group sizes,
and measurement scale. A small p-value with a small effect can be statistically
detectable but practically modest. A large effect with a wide interval can be
uncertain, especially in small samples.

## Limitations

Effect-size labels are generic thresholds. They are not biological thresholds
and do not define importance for a particular marker or experiment. Effect sizes
also inherit the assumptions of the measurement table: missing rows, repeated
ROI rows, non-independent subjects, or strong outliers can change the estimate.

Bootstrap confidence intervals are data-driven intervals. They can be unstable
when sample sizes are small, values are tied, or groups have little variation.

## See Also

- [Group Comparisons](group-comparisons.md)
- [Power](power.md)
- [plot_effect_forest](../functions/plot_effect_forest.md)
- [plot_group_matrix](../functions/plot_group_matrix.md)
