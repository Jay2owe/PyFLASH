# First Plot Spec

## Goal

Run a reusable declarative plot spec instead of writing one Python call per
plot.

## Before You Start

- Create or load a PyFLASH object first.
- Use registry names such as `mean_bars`, not Python function names such as
  `plot_mean_bars`.
- YAML specs need PyYAML. The local `.[ui]` extra includes it.
- TOML specs use Python's built-in `tomllib` on Python 3.11 and newer. On
  Python 3.9 or 3.10, install `tomli`.
- JSON specs work without extra packages.

## Steps

Create a file named `plots.yaml`:

```yaml
plots:
  - type: mean_bars
    columns:
      - GFAP Volume
    save: false
    save_normality: false
```

Run it from Python:

```python
from PyFLASH import load_state, run_spec

batch = load_state(r"C:\path\to\pickles\Example.pkl")
results = run_spec(batch, r"C:\path\to\plots.yaml")

print(results)
```

For multiple loaded objects, pass a dictionary and select one in the spec:

```yaml
plots:
  - type: mean_bars
    batch: cohort_1
    columns:
      - GFAP Volume
    save: false
```

```python
results = run_spec({"cohort_1": batch}, r"C:\path\to\plots.yaml")
```

## Check It Worked

- `run_spec` returns a list with one result per plot entry.
- Validation errors stop the run and explain what to fix.
- A failed plot entry returns `None`, but later entries can still run.

## Next

- [run_spec](../functions/run_spec.md)
- [API reference](../api-reference.md#plotting-registry)
- [First plot](first-plot.md)
