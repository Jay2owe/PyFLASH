# Plot From A Spec

## Goal

Run a repeatable batch of plots or pipeline calls from a YAML, TOML, or JSON
file with [`run_spec`](../functions/run_spec.md).

Use this workflow when you want a saved recipe that can be rerun on the same
data or shared with collaborators.

## Inputs

- A loaded PyFLASH object, raw DataFrame, or dictionary of named data sources.
- A spec file with a top-level `plots` list.
- A registered `type` for each entry, such as `mean_bars`,
  `correlation_pipeline`, `linear_model_pipeline`, or
  `iterative_model_sweep`.
- Parameters accepted by the target plot or pipeline.

## Minimal Path

```python
from PyFLASH import load_state, run_spec

batch = load_state(r"C:\path\to\pickles\SCN_Diagnosis.pkl")
results = run_spec(batch, r"C:\path\to\plot-specs\summary-plots.yaml")

print(len(results))
```

Example `summary-plots.yaml`:

```yaml
plots:
  - type: mean_bars
    data_cols:
      - GFAP Volume
    save: false
```

## Full Workflow

1. Decide which object or objects the spec should run against.

```python
from PyFLASH import load_state

human = load_state(r"C:\path\to\pickles\human.pkl")
mouse = load_state(r"C:\path\to\pickles\mouse.pkl")
```

2. Write a spec with one entry per plot or pipeline:

```yaml
plots:
  - type: mean_bars
    batch: human
    data_cols:
      - GFAP Volume
      - IBA1 Volume
    save: true

  - type: correlation_pipeline
    batch: human
    data_cols:
      - GFAP Volume
      - IBA1 Volume
      - DAPI Count
    tests:
      - pearsonr
      - spearmanr
    require: or
    gate: p
    max_regressions: 6
    run_label: marker_correlations
    if_exists: version
    save: true

  - type: matrices
    batch: mouse
    data_cols:
      - GFAP Volume
      - IBA1 Volume
    split_by: Diagnosis
    save: true
```

3. Run the spec against a dictionary when entries use `batch:`:

```python
from PyFLASH import run_spec

results = run_spec(
    {"human": human, "mouse": mouse},
    r"C:\path\to\plot-specs\comparison.yaml",
)
```

4. Use JSON when you need a format that works without PyYAML:

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

5. Inspect the result list. A failed entry contributes `None`, while later
   entries continue.

```python
for index, result in enumerate(results):
    print(index, "failed" if result is None else type(result).__name__)
```

## Outputs

`run_spec` returns a list with one item per spec entry. The item is whatever the
target callable returned, or `None` if that entry failed during execution.

`run_spec` itself does not create files. Saved files come from the plot or
pipeline entries:

- plot functions with `save: true` write figures below the object's figure
  path;
- pipeline entries write run folders with CSV files, `manifest.json`, run
  indexes, and often `! Overview Montage.png`;
- entries with `save: false` compute and return Python results without saved
  figures.

## Troubleshooting

- `unknown plot type`: check the registry key in
  [plot spec files](../data-structures/plot-spec-files.md) or
  [API reference](../api-reference.md).
- Missing `batch`: when `run_spec` receives a dictionary, every named entry
  should use a valid `batch:` key unless you intentionally want the first data
  source.
- Unknown parameter warnings: compare the entry with the target function page.
  Common friendly aliases such as `data_cols`, `group_col`, `subject_col`, and
  `filter_by` are supported.
- YAML load errors: install PyYAML or use `.json`.
- Missing column warnings: inspect the input object's `.summary.columns`.

## Next Steps

- [run_spec reference](../functions/run_spec.md)
- [Plot spec files](../data-structures/plot-spec-files.md)
- [Plot from Python](plot-from-python.md)
- [Run correlation pipeline](run-correlation-pipeline.md)
- [Saving and run labels](../parameters/saving.md)
- [Invalid plot spec troubleshooting](../troubleshooting/invalid-plot-spec.md)
