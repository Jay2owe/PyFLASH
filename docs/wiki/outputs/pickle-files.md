# Pickle Files

## Summary

Pickle files save the Python state of a processed PyFLASH object. They are the
fastest way to reopen a `Batch`, `Experiment`, `MiniExperiment`, or
`DataFrameExperiment` without re-importing the original ImageJ/FLASH outputs.

Use pickles for your own analysis sessions and UI workflows. Use CSV, Excel,
or pipeline run folders when collaborators need portable, non-Python outputs.

## Created By

| Function or workflow | What it writes or reads |
|---|---|
| [`save_state`](../functions/save_state.md) | Writes one `.pkl` file to the explicit `filename`, or to `obj.csv_path / f"{obj.name}.pkl"` when `filename=None`. |
| [`load_state`](../functions/load_state.md) | Reads a `.pkl` file, records `_state_path`, optionally rebases stale paths, and can resave after migration or rebasing. |
| [`normalize_paths`](../functions/normalize_paths.md) | Rebases paths on an object already in memory; does not write unless you call `save_state` afterward. |
| `create_batch(..., pickle_path=...)` | Uses `<pickle_path>/<name>.pkl` as a cache. Loads it when present and `rerun=False`; saves it after processing when a cache path is supplied. |
| UI project/export flows | Call the same `load_state` and `save_state` helpers through the UI service layer. |

## Folder Layout

Explicit save:

```text
analysis-output/
  pickles/
    scn_batch.pkl
```

`create_batch(..., pickle_path="analysis-output/pickles")`:

```text
analysis-output/
  pickles/
    <batch-name>.pkl
```

`save_state(batch)` with `filename=None`:

```text
<batch-output>/Results/Separate CSVs/
  <batch-name>.pkl
```

That default requires the object to have both `csv_path` and `name`.

## File Contents

A pickle stores Python object state, not a folder of tables. For a `Batch`, that
can include:

| State | Meaning |
|---|---|
| `summary` and `summaries` | Processed batch summary tables. |
| `data` | Imported marker/behavior objects and their tables. |
| `condition_list`, `conditions`, `factor`, `factorDict` | Condition metadata used by plots and exports. |
| Output paths | Paths such as `fig_path`, `data_path`, `export_path`, and `csv_path`. |
| User selections | State such as representative image selections when present. |

`Batch.__getstate__` strips bulky image-cache fields such as `images`,
`imagesDict`, `image_root`, and `var_name` before pickling. Old inline image
arrays are stripped on load if they are found in legacy pickles.

`save_state` records `obj._state_path = filename` before writing.

## How To Reuse

Create or reuse a cached batch:

```python
from PyFLASH import create_batch

batch = create_batch(
    name="scn_batch",
    conditions=conditions,
    batch_path="analysis-output",
    experiments="analysis-input/experiments",
    pickle_path="analysis-output/pickles",
)
```

Save and load an explicit pickle:

```python
from PyFLASH import save_state, load_state

save_state(batch, "analysis-output/pickles/scn_batch.pkl")
batch = load_state("analysis-output/pickles/scn_batch.pkl")
```

Rebase paths after moving a project:

```python
from PyFLASH import load_state, save_state

batch = load_state(
    "analysis-output/pickles/scn_batch.pkl",
    normalize_paths=True,
    resave_if_rebased=True,
)
print(batch.fig_path)
```

Normalize an already loaded object and then save it:

```python
from PyFLASH import normalize_paths, save_state

changed = normalize_paths(batch)
if changed:
    save_state(batch, "analysis-output/pickles/scn_batch.pkl")
```

## Notes

- `load_state` uses a PyFLASH-aware unpickler that can remap old
  `IF_analysis...` module paths to current `PyFLASH...` module paths.
- `load_state(normalize_paths=True)` checks the loaded object and nested
  experiments for stale `filePath` values, then refreshes derived save paths by
  calling `createSavePaths()` when possible.
- `load_state(..., resave_if_rebased=False)` can update paths in memory without
  overwriting the pickle.
- `load_state` may overwrite a pickle when it removes legacy image arrays,
  migrates old `_expN` batch-summary suffixes to `.expN`, removes an obsolete
  `<filename>.images.pkl` sidecar, or when `resave_if_rebased=True`.
- A pickle created with one package version may not be a stable long-term public
  archive. Keep CSV/Excel/pipeline outputs for durable sharing.

## See Also

- [save_state](../functions/save_state.md)
- [load_state](../functions/load_state.md)
- [normalize_paths](../functions/normalize_paths.md)
- [Where results go](../getting-started/where-results-go.md)
