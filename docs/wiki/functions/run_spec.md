# run_spec

## Summary

`run_spec` loads a YAML, TOML, or JSON plot specification and executes each
registered plot entry against one data object or a named dictionary of data
objects.

Use it when you want a repeatable batch of plots or pipeline calls without
writing a full Python script. Each spec entry names a registry `type`, optional
`batch`, and the parameters to pass to that registered callable.

## Signature

```python
run_spec(experiments, path)
```

## Input Object Types

| Object type | Accepted? | Notes |
|---|---:|---|
| `Batch` | Yes | Main input for imported PyFLASH workflows. |
| `Experiment` | Yes | Works for registered functions that accept a single experiment-like object. |
| `MiniExperiment` | Yes | Works for summary-based registered functions. |
| `DataFrameExperiment` | Yes | Works for summary plots and pipelines that use `.summary`. |
| `pandas.DataFrame` | Yes | Works only for registered callables that accept raw DataFrames or call `from_dataframe` internally. |
| `dict[str, object]` | Yes | Maps names to data objects. Spec entries can select one with `batch: name`. |

## Parameters

| Parameter | Type | Default | Meaning |
|---|---|---:|---|
| `experiments` | object or `dict[str, object]` | required | Data source for every entry, or name-to-source mapping for multi-source specs. |
| `path` | Path-like | required | Spec file with extension `.yaml`, `.yml`, `.toml`, or `.json`. |

## Returns

| Return value | Type | Meaning |
|---|---|---|
| `results` | `list` | One item per `plots` entry. Each item is the target callable's return value, or `None` if that entry raised during execution. |

## Saved Outputs

`run_spec` itself does not write figures or tables. Saved outputs are controlled
by the registered callable and the parameters in each spec entry.

Common patterns:

- plot entries with `save: true` write figures under the input object's figure
  folder or a function-specific `save_path`;
- pipeline entries can write run folders, CSV tables, manifests, and montages;
- entries with `save: false` usually compute and return Python objects without
  writing plot files.

## Examples

### Minimal YAML spec

```python
from PyFLASH import run_spec

results = run_spec(batch, "plots.yaml")
print(len(results))
```

```yaml
plots:
  - type: mean_bars
    data_cols:
      - GFAP Volume
    save: false
```

### Run a spec against a raw DataFrame

```python
from PyFLASH import run_spec

results = run_spec(df, "plots.json")
```

```json
{
  "plots": [
    {
      "type": "mean_bars",
      "data_cols": ["GFAP Volume"],
      "group_col": "Diagnosis",
      "subject_col": "Subject ID",
      "save": false
    }
  ]
}
```

### Multi-source spec

```python
from PyFLASH import run_spec

results = run_spec(
    {
        "human": human_batch,
        "mouse": mouse_batch,
    },
    "comparison-plots.yaml",
)
```

```yaml
plots:
  - type: mean_bars
    batch: human
    data_cols: [GFAP Volume]
    save: true

  - type: matrices
    batch: mouse
    data_cols: [GFAP Volume, Iba1 Volume]
    split_by: Diagnosis
    save: true
```

### Inspect failures without losing successful results

```python
from PyFLASH import run_spec

results = run_spec(batch, "plots.yaml")
for index, result in enumerate(results):
    if result is None:
        print(f"plots[{index}] failed")
    else:
        print(f"plots[{index}] returned {type(result).__name__}")
```

## Notes

- The spec root must be a dictionary with a `plots` list. Each entry must be a
  dictionary with a registered `type`.
- `type` must be a key in `PyFLASH.spec.PLOT_REGISTRY`, such as `mean_bars`,
  `regressions`, `correlation_pipeline`, or `data_overview_pipeline`.
- Validation errors stop the whole run before any entry executes. Examples:
  missing `plots`, non-list `plots`, missing `type`, unknown `type`, or a
  `batch` name not present in the `experiments` dictionary.
- Validation warnings are logged but do not stop execution. Examples include
  unknown parameter names or exact column names that are absent from the input
  summary.
- Per-entry execution errors are caught. The failed entry contributes `None` to
  the returned `results` list and later entries continue.
- If `experiments` is a dictionary and an entry omits `batch`, PyFLASH uses the
  first data source and logs a warning.
- Spec aliases are resolved against the target function signature. Common
  aliases include `data_cols -> filtered_columns`, `against_data_cols ->
  against_columns`, `group_col -> condition_col`, `group_cols -> factor_cols`,
  `subject_col -> animal_col`, `filter_by -> specificity`, and `subjects ->
  animals`.
- `specificity` and `filter_by` list or mapping forms are converted from
  YAML/JSON-friendly values to the Python shapes expected by plotting code.
- YAML files require PyYAML. TOML files use `tomllib` on Python 3.11+ or
  `tomli` on older Python versions.

## See Also

- [Plot spec files](../data-structures/plot-spec-files.md)
- [Plot from spec workflow](../workflows/plot-from-spec.md)
- [Saving parameters](../parameters/saving.md)
- [Plot types](../plot-types/README.md)
- [API reference](../api-reference.md)
