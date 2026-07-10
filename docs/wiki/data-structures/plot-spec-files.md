# Plot Spec Files

## Summary

Plot spec files are YAML, TOML, or JSON files executed by
[`run_spec`](../functions/run_spec.md). They let you batch one or more plot or
pipeline calls without writing a full Python script.

The spec runner reads a file, validates plot names and common parameters, maps
friendly aliases to actual function parameters, then calls each registered
plot or pipeline in order.

## Where It Appears

- Files passed to `run_spec(experiments, path)`.
- UI plot-spec workflows that validate and run a saved spec.
- Agent/runner requests that call registered plot or pipeline aliases.
- Gallery and workflow examples.

## Required Fields

At the file root:

| Key | Meaning |
|---|---|
| `plots` | A list of plot entries. |

For each entry:

| Key | Meaning |
|---|---|
| `type` | Plot or pipeline short name registered in `PLOT_REGISTRY`, such as `mean_bars`, `correlation_pipeline`, or `data_overview_pipeline`. |

When `run_spec` receives a dictionary of data sources, each entry can also use:

| Key | Meaning |
|---|---|
| `batch` | Name of the data source to use from the dictionary passed to `run_spec`. |

## Optional Fields

Every other key is treated as a function parameter after alias resolution. The
available keys depend on the chosen `type`.

Common aliases include:

| Spec Key | Passed As |
|---|---|
| `columns`, `data_cols` | `filtered_columns` |
| `data_col_contains` | `column_strings` |
| `data_col_regex` | `regex_string` |
| `data_col_exclude` | `exclude` |
| `against_data_cols` | `against_columns` |
| `leading_data_cols` | `first_columns` |
| `filter_by` | `specificity` |
| `groups`, `group_list` | `conditions` |
| `group_col` | `condition_col` |
| `group_cols` | `factor_cols` |
| `subject_col` | `animal_col` |
| `subjects` | `animals` |
| `show_subject_points` | `show_animal_xs` |

`filter_by` is the preferred row-filter key and accepts these JSON/YAML-safe
forms. Older spec files may use the legacy/internal key `specificity` with the
same forms:

| Form | Meaning |
|---|---|
| `["Time", "WeekEight"]` | One filter tuple. |
| `[["Time", "WeekEight"], ["Region", "CA1"]]` | A legacy tuple-style filter queue. |
| `{"Sex": "Female", "Region": "SCN"}` | An AND filter mapping. |
| `[{"Sex": "Female", "Region": "SCN"}, {"Sex": "Male", "Region": "SCN"}]` | Queue of AND filters. |

## Example

```yaml
plots:
  - type: mean_bars
    data_cols:
      - GFAP Volume
    group_col: Diagnosis
    subject_col: AnimalName
    save: true

  - type: correlation_pipeline
    data_cols:
      - GFAP Volume
    against_data_cols:
      - IBA1 Volume
    filter_by:
      Region: SCN
    tests:
      - pearsonr
    save: true
```

Equivalent JSON shape:

```json
{
  "plots": [
    {
      "type": "mean_bars",
      "data_cols": ["GFAP Volume"],
      "group_col": "Diagnosis",
      "subject_col": "AnimalName",
      "save": false
    }
  ]
}
```

## Produced By

- Users writing plot batches by hand.
- UI workflows that save a plot-spec JSON file.
- Agent-generated reproducibility snippets.

## Consumed By

- [`run_spec`](../functions/run_spec.md).
- UI service functions that validate and run plot specs.
- The plot registry in `PyFLASH.spec.PLOT_REGISTRY`.

## Notes

- Supported file extensions are `.yaml`, `.yml`, `.toml`, and `.json`.
- YAML specs require PyYAML to be installed. TOML uses `tomllib` on Python 3.11+ or `tomli` on older Python versions.
- Validation errors block execution when the root shape is wrong, a plot `type` is missing or unknown, or a named `batch` does not exist.
- Unknown parameter names are warnings when the target function signature can be inspected.
- Missing columns in a data source are warnings, not immediate errors, because some specs use selectors rather than exact column names.
- `run_spec` returns one result per plot entry. A failed entry is represented by `None` in the result list.

## See Also

- [Run spec](../functions/run_spec.md)
- [Plot from spec workflow](../workflows/plot-from-spec.md)
- [Column selection](../parameters/column-selection.md)
- [Filter By](../parameters/specificity.md)
