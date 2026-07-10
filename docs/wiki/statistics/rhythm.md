# Rhythm

## Summary

PyFLASH rhythm statistics describe time-of-day or phase-related patterns. The
main methods are cosinor models for rhythmic numeric measurements and circular
statistics for phase or acrophase values.

## Where PyFLASH Uses It

- [rhythm](../functions/rhythm.md) runs cosinor and phase-parameter pipelines.
- [plot_cosinor](../functions/plot_cosinor.md) fits and draws cosinor curves.
- [plot_acrophase_clock](../functions/plot_acrophase_clock.md) draws circular
  phase summaries.
- [plot_timecourse](../functions/plot_timecourse.md) can display timecourse
  data that may later be tested with rhythm tools.

## Inputs

Cosinor inputs include one or more numeric columns, a time column, an optional
group column, and a period. Fixed-period cosinor requires enough time points to
fit mesor, sine, and cosine terms. Free-period exploratory fitting also estimates
period.

Phase-mode inputs include a phase or acrophase column in circular units, an
optional group column, and optional scalar parameter columns. Scalar parameters
can be compared across ordered or unordered groups.

The cosinor table can use pooled, population-mean, or mixed strategies. If an
animal column is needed for a population or mixed strategy but is not supplied,
PyFLASH falls back to pooled fitting and records that route.

## Outputs

Cosinor outputs can include:

- `mesor`: fitted rhythm-adjusted mean level.
- `amplitude`: half the fitted peak-to-trough range.
- `acrophase`: fitted phase of the peak.
- period or `tau` where free-period fitting is used.
- rhythm p-values and optional q-values during screening.
- group-test rows comparing common versus group-specific sine and cosine terms.

Circular outputs can include:

- circular mean phase.
- resultant length, a concentration measure from 0 to 1.
- Rayleigh-test output for non-uniformity in a single group.
- Watson-Williams-style group mean phase tests for multiple groups.
- Wallraff-style dispersion comparisons using angular deviations.
- optional scalar parameter tests and trend summaries.

## Interpretation

A cosinor rhythm p-value tests whether the fitted sine and cosine terms improve
the model over a flat pattern for the chosen period. The group cosinor test asks
whether allowing group-specific rhythmic terms improves fit; it is a combined
test of rhythmic shape differences and does not isolate a single biological
cause.

Acrophase is circular. A difference near the wrap point can look numerically
large while being close on the circle, so use the circular summaries and clock
plots rather than ordinary subtraction alone.

## Limitations

Cosinor models assume a sinusoidal pattern for the tested period. Sparse time
sampling, uneven group sizes, outliers, and missed peaks can make amplitude and
acrophase unstable. Free-period fits are exploratory; their omnibus p-values are
approximate and should be treated cautiously.

Circular group tests assume that the circular summaries are meaningful for the
data. Very dispersed phases, multimodal phase distributions, and small groups
can make mean-phase tests hard to interpret.

## See Also

- [Multiple Testing](multiple-testing.md)
- [Structured Results](structured-results.md)
- [rhythm](../functions/rhythm.md)
- [plot_cosinor](../functions/plot_cosinor.md)
- [plot_acrophase_clock](../functions/plot_acrophase_clock.md)
