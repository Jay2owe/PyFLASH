# Power

## Summary

Power tools estimate the probability of detecting an effect under a specified
test model, effect size, alpha, and sample size. PyFLASH uses power calculations
as planning and diagnostic summaries, not as proof that an observed result is
true or false.

## Where PyFLASH Uses It

- [plot_power_curve](../functions/plot_power_curve.md) draws expected power
  across sample sizes and effect sizes.
- [group_comparison](../functions/group_comparison.md) can report achieved
  power and estimated sample size required for 80 percent power.
- [data_overview](../functions/data_overview.md) can report minimum detectable
  effect summaries for marker contrasts.

## Inputs

Power calculations need an effect size, alpha, sample size, and test family. The
main helper functions use two-sample t-test assumptions for standardized
differences. Plot-level power curves can also draw ANOVA-style curves depending
on the requested configuration.

For group-comparison outputs, observed data are used to estimate an observed
effect size and current sample sizes. Required sample size estimates are
reported per group under the configured target power.

## Outputs

Power-related outputs can include:

- `achieved_power`: estimated power for the observed sample size and effect.
- `required_n_80`: estimated per-group sample size for 80 percent power.
- `effect_size`, `n_per_group`, and `power` rows from power-curve tables.
- minimum detectable effect summaries in data-overview outputs.
- power-curve figures and optional CSV tables.

## Interpretation

Power is a model-based planning quantity. A higher value means the specified
analysis would more often detect the specified effect if the assumptions held.
Required sample size estimates are useful for planning similarly structured
future experiments.

Post-hoc achieved power is descriptive. It is largely a transformation of the
observed effect and sample size, so it should not be used as independent
evidence that a non-significant result proves no difference.

## Limitations

Power estimates depend strongly on assumptions about variance, independence,
effect size, alpha, balance, and the selected test. Estimates from small pilot
datasets can be noisy. ROI-level rows should not be treated as independent
subjects unless the analysis design supports that.

Data-overview minimum detectable effect summaries are screening aids. They are
not substitutes for a prospective power analysis matched to the final design.

## See Also

- [Effect Sizes](effect-sizes.md)
- [Group Comparisons](group-comparisons.md)
- [plot_power_curve](../functions/plot_power_curve.md)
- [data_overview](../functions/data_overview.md)
