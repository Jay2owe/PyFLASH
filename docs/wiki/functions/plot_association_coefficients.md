# plot_association_coefficients

Plot several fitted relationships across the same groups. Each marker is a
group's slope; its bracket is a confidence interval for that slope. The
statistics panel separately explains slope comparisons and the overall test.

Registered plot name: `association_coefficients`.

## Inputs and models

Accepts `Batch`, `Experiment`, `MiniExperiment`, `DataFrameExperiment`,
or a raw `pandas.DataFrame`. Experiment objects supply their summary tables;
raw frames use the normal dataframe adapter with `group_col`, `subject_col`
and other grouping arguments. This function fits subject-level observations;
it does not accept a CSV filename or precomputed coefficient table directly.
Load a CSV with `pandas.read_csv` first.

`associations` is an ordered mapping of labels to specifications containing
`x`, `y` and optional `covariates`. A list of specifications is also
supported; labels are inferred from the columns unless supplied.

Each association fits `y ~ x * group + covariates` across all included groups.
Numeric covariates are additive; categorical covariates are encoded as factors.
All associations share one complete-case cohort: rows missing any required
predictor, outcome or covariate are excluded from every model.
`group_order` controls the displayed groups; `reference` defaults to the
first group. `min_n=4` is the minimum complete observations per group.

## Example

```python
from PyFLASH.plotting import plot_association_coefficients

result = plot_association_coefficients(
    frame,
    associations={
        "Dose-response": {
            "x": "Dose", "y": "Response", "covariates": ["Batch"],
        },
        "Response-activity": {
            "x": "Response", "y": "Activity", "covariates": ["Dose", "Batch"],
        },
    },
    factor="Arm",
    group_col="Arm",
    subject_col="Subject",
    group_order=["Baseline", "Treatment A", "Treatment B"],
    reference="Baseline",
    save=False,
    return_data=True,
)
```

## Estimates and intervals

`value="beta"` plots standardized slopes: outcome standard deviations per
predictor standard deviation, using scaling across all included groups.
`value="slope"` plots slopes in the original outcome-per-predictor units.

`ci_method="bootstrap"` uses group-stratified bootstrap intervals by default;
`ci_method="ols"` uses ordinary least-squares (OLS) t intervals.
`ci_alpha=0.05` gives 95% confidence intervals. Bootstrap defaults are
`bootstrap_resamples=5000` and `random_state=0`.

A group-slope interval is not an interval for the difference between groups.
Whether one interval crosses zero does not determine whether two groups'
slopes differ.

## Reference comparisons

`comparison_test="bootstrap_wald"` is the default. It tests each non-reference
interaction from the pooled, all-group model with a two-sided Wald z test,
using its bootstrap standard error.

`comparison_test="ols_t"` instead fits a separate two-group OLS model for each
group/reference pair, with the same association-specific covariates and the
same shared complete-case cohort. `comparison_tail` selects the alternative
for group slope minus reference slope:

- `"two"` (default): any non-zero difference.
- `"less"`: the group's slope is lower than the reference slope.
- `"greater"`: the group's slope is higher than the reference slope.

Directional alternatives require `"ols_t"` and should represent a hypothesis
chosen before inspecting the data. There is no automatic observed-direction
option. P-values are nominal, with no correction for multiple comparisons.

For a prespecified lower-slope hypothesis, add:

```python
comparison_test="ols_t",
comparison_tail="less",
```

In standardized mode, two-group fits scale their predictor and outcome within
that pair. Their reported `delta` therefore need not equal the subtraction of
the displayed slopes, which use all-group scaling. The panel states this
distinction and the number of participants used by each comparison.

Selecting a comparison test changes neither plotted slopes and intervals nor
the overall joint test. The latter remains a bootstrap Wald chi-square test
of all predictor-by-group interaction terms across all associations; its
sample size covers the full shared cohort.

## Statistics panel and fixed dimensions

The removable right-side panel separates:

- Models, group estimates, confidence intervals and group sample sizes.
- Selected group/reference tests, their alternatives, differences, test
  statistics, degrees of freedom and model sample sizes.
- The overall joint test and bootstrap settings.

No statistical p-value or test readout is added to the title or subtitle.
`show_stats_summary=False` hides the panel.
`stats_summary_max_items=10` caps each list of estimates/comparisons and
reports omitted rows; full results remain in returned tables and report records.

The figure reserves the same two-column statistics area even when the panel is
hidden. Statistics visibility, selected test and text length do not resize
the canvas or the plotting axes. Saving through `PyFLASH.utils.save_fig`
preserves these bounds in SVG and raster exports, including when the global
save setting requests a tight bounding box.

`show_values=False` hides the compact coefficient labels near the markers.
`column_labels` changes displayed column names without changing data identity.

## Filtering, saving and returned results

`specificity`/`filter_by` filter rows; lists run a filter queue.
`roi` selects region-of-interest summaries; a list runs a region queue.
`by`/`split_by` and `factor` use the normal grouping aliases.
The plot inherently combines group levels, so there is no `combine` parameter.

With `save=True` (default), exports go through the shared PyFLASH exporter
under `Association Coefficients/`. With `return_data=False` (default), the
function returns the figure; queue calls return dictionaries of results.
`return_data=True` returns:

- `figure`: the rendered figure.
- `coefficients`: plotted slopes, intervals, sample sizes and interval method.
- `interactions`: the original pooled bootstrap interaction table.
- `comparisons`: the selected reference-comparison table, with method, tail,
  model scope and group/reference counts.
- `joint_test`: the overall bootstrap Wald result.
- `bootstrap`: requested/valid resample counts and seed.

When the report collector is active, group estimates, pooled interactions,
selected comparisons and the overall test are captured as structured results.

## See also

- [Regression plots](../plot-types/regression-plots.md)
- [Coefficient contrasts](plot_coefficient_contrast.md)
- [Structured results](../statistics/structured-results.md)
