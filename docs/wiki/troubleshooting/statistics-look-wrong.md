# Statistics Look Wrong

## Symptoms

- A p-value is missing, or an annotation reads `N/A` instead of a test result.
- The test switched between parametric and non-parametric unexpectedly.
- A group-comparison figure looks purely descriptive when you expected p-values.
- Numbers change after adding `filter_by`, `exclude`, an ROI, or excluding
  subjects.
- A model sweep prefers a surprising feature set.

## Likely Causes

- A group had too few usable numbers. The shared comparison engine coerces each
  group to numeric and drops non-numeric text, NaN, and excluded values; a group
  that ends up with 0 values is dropped, and with fewer than two valid groups no
  test runs (you see `N/A`).
- Excluded values are analysis-missing by design. Cells holding an `EXCLUDED_`
  sentinel (auto outliers or manual exclusions) and `NOT_INCLUDED_IN_EXPERIMENT`
  are treated as missing by every numeric path, so they reduce group `n`.
- Normality diagnostics are descriptive for some two-group plot annotations in
  the current shared comparison engine. The common two-group branch still uses
  its independent-test path when both groups have more than one valid value;
  multi-group and pipeline paths can use different routing.
- A multiple-testing correction was applied, so annotations show corrected
  q-values rather than raw p-values.
- A descriptive plot was used for an inferential question. `plot_superplot`,
  `plot_effect_forest`, and `plot_group_matrix` show raw points and effect
  sizes but run no test — the significance tables come from the
  `group_comparison` pipeline.

## Fix

Confirm the counts and values actually entering each group before reading the
p-value:

```python
cols = [c for c in ["AnimalName", "Condition"] if c in batch.summary.columns]
print(batch.summary[cols].drop_duplicates().groupby("Condition").size())
print(batch.summary[["GFAP_Count"]].describe())
```

If a group looks short, check for excluded cells and confirm your row filters
did not remove more than intended. If you need a specific inferential route,
prefer the `group_comparison` pipeline or inspect the saved statistics CSVs
rather than relying on figure annotations alone.

## Check

Compare `n` per group before and after a filter, and open the run folder's CSVs
and `manifest.json` for pipelines. Raw p-values are primary in PyFLASH;
corrected q-values appear only where a correction step is enabled.

## Related Pages

- [Group comparisons](../statistics/group-comparisons.md)
- [Multiple testing](../statistics/multiple-testing.md)
- [Statistics options](../parameters/statistics-options.md)
- [exclusions](../functions/exclusions.md)
- [Exclusion ledgers](../data-structures/exclusion-ledgers.md)
- [Normality outputs](../outputs/normality-outputs.md)
