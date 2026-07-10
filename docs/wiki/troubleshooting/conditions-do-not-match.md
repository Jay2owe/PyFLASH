# Group Labels Do Not Match

## Symptoms

- Plots group subjects under the wrong label, or a group comes out empty.
- A comparison does not involve the groups you expected.
- Building groups raises `Condition '<name>' not found.` (often with a
  `Did you mean '...'?` suggestion).
- A raw DataFrame call raises `factor_cols not found in DataFrame: [...]` or
  `DataFrame input must include a Condition column, a condition_col, or all
  factor columns from the supplied conditions.`
- A crossed design produces too many, too few, or differently ordered groups.

## Likely Causes

- The group **short name** in the builder does not match the value in the
  data. Matching is case- and whitespace-insensitive, but not fuzzy: `AD ` and
  `ad` match, `AlzD` does not match `AD`.
- The internal `Condition` group column was parsed from folder names differently than the
  builder's short names expect.
- For a raw DataFrame, `group_col`/`group_cols` (or `subject_col`) point at a
  column that is absent or spelled differently.
- A crossed comparison reuses a short name across both factors and needs a
  `within_factor` to disambiguate.
- The batch was built or pickled before the group spec was corrected, so it
  still carries the old group list.

## Fix

Compare the built short names against the values actually in the table:

```python
print([c.name for c in batch.condition_list])
print(batch.summary["Condition"].dropna().unique())
```

Make the two sets agree — fix the builder short name or map the raw value with
`factor_mappings` / `condition_labels`. For a raw DataFrame, name the grouping
columns so the adapter can derive `Condition`:

```python
from PyFLASH import data_overview

data_overview(
    df,
    data_cols=["GFAP_Count"],
    group_cols=["Diagnosis", "Sex"],   # crossed design; both columns must exist
    subject_col="AnimalName",
    save=False,
)
```

If a comparison name is misspelled, the builder's `Did you mean '...'?`
suggestion names the closest valid short name. After changing any group
definition, rebuild or reload the batch — an existing pickle keeps the group
list it was saved with.

## Check

Inspect grouping columns together, then the resolved comparisons:

```python
cols = [c for c in ["AnimalName", "Condition", "Diagnosis", "Sex", "Time"]
        if c in batch.summary.columns]
print(batch.summary[cols].drop_duplicates())
print(batch.condition_list.comparisons)   # e.g. ['1-2', '1-3']
```

Comparisons are one-based index strings into the current group order in
`batch.condition_list`. If the order changed, the numbers point at different
groups.

## Related Pages

- [Groups and factors](../parameters/conditions-and-factors.md)
- [Build groups](../workflows/build-conditions.md)
- [Group specs](../data-structures/condition-specs.md)
- [Groups object](../object-types/conditions.md)
- [Input objects](../parameters/input-objects.md)
