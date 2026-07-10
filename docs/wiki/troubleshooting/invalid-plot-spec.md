# Invalid Plot Spec

## Symptoms

- `run_spec` raises `ValueError: Spec validation failed with N error(s).`.
- Validation reports `Spec must be a dict with a 'plots' key` or
  `'plots' must be a list of plot entries`.
- An entry reports `missing 'type' field` or
  `unknown plot type '<name>'. Available: ...`.
- An entry reports `batch '<name>' not found. Available: ...`.
- Validation succeeds with warnings, but an individual plot result comes back as
  `failed`.

## Likely Causes

- The top-level document is a bare list instead of a mapping with a `plots`
  key.
- The `type` value is not one of the short names in `PLOT_REGISTRY`.
- The spec references `batch: <name>` but the batch mapping passed to `run_spec`
  has no such key.
- A parameter name is misspelled or belongs to a different plot function. These
  are warnings, not errors, so the run proceeds and the entry may fail at call
  time.
- The file extension does not match the contents, or YAML support is missing
  (`ImportError: PyYAML is required to load .yaml spec files.`).

## Fix

Shape the file as a mapping with a `plots` list, one entry per plot, each with a
`type`:

```yaml
plots:
  - type: mean_bars
    data_cols: [GFAP_Count, Iba1_Count]
    save: true
```

Check the `type` against the registry short names, and prefer current parameter
names (`data_cols`, `filter_by`, `split_by`, `group_col`, `group_cols`,
`subject_col`) — the spec runner maps them to the internal names automatically:

```python
from PyFLASH.ui import services

print(services.available_plots())   # sorted PLOT_REGISTRY short names
```

Errors (bad structure, unknown `type`, unresolved `batch`) block the whole run.
Warnings (unknown parameter, a column not found in `experiment.summary`) do not
block; `run_spec` still executes each entry and returns `None` for any entry
whose call raised, so one bad entry never aborts the others.

## Check

Validate before running so you see errors and warnings separately:

```python
from PyFLASH.spec import load_spec, validate_spec, run_spec

spec = load_spec("path/to/plots.yaml")
errors, warnings = validate_spec(spec, batch)
print("errors:", errors)
print("warnings:", warnings)

if not errors:
    print(run_spec(batch, "path/to/plots.yaml"))
```

## Related Pages

- [Plot spec files](../data-structures/plot-spec-files.md)
- [Plot from a spec](../workflows/plot-from-spec.md)
- [run_spec](../functions/run_spec.md)
- [Plot registry](../developer/plot-registry.md)
- [Column selection](../parameters/column-selection.md)
