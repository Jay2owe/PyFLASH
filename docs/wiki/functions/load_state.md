# load_state

## Summary

`load_state` reads a PyFLASH pickle file and returns the saved object. It is the
normal way to reopen a processed `Batch` or `Experiment` without reprocessing
the original FLASH/ImageJ folders.

By default, it also tries to repair stale absolute paths in the loaded object.
That matters when a pickle was created on another machine, under another user
folder, or before the package rename from `IF_analysis` to `PyFLASH`.

## Signature

```python
load_state(filename, normalize_paths=True, resave_if_rebased=False, verbose=True)
```

## Input Object Types

| Object type | Accepted? | Notes |
|---|---:|---|
| Path-like `.pkl` file | Yes | Required as `filename`. |
| `Batch` | Returned | Main saved state for full workflows. |
| `Experiment` | Returned | Returned when the pickle contains one experiment. |
| `MiniExperiment` | Returned | Returned when the pickle contains a table-based experiment. |
| `DataFrameExperiment` | Returned | Returned when the pickle contains a wrapped DataFrame object. |
| `pandas.DataFrame` | No | A bare table pickle is not the public PyFLASH state format. |

## Parameters

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `filename` | Path-like | required | Pickle file to read. |
| `normalize_paths` | `bool` | `True` | Rebase stale `filePath` values with PyFLASH's directory resolver and refresh derived save paths. |
| `resave_if_rebased` | `bool` | `False` | If path normalization changed a root path, overwrite the pickle with the updated paths. |
| `verbose` | `bool` | `True` | Print loaded object name, data keys, summary shape, and condition names when available. |

## Returns

| Return value | Type | Meaning |
|---|---|---|
| `obj` | `Batch`, `Experiment`, `MiniExperiment`, `DataFrameExperiment`, or another pickled object | Loaded object. PyFLASH records `obj._state_path = filename` before returning it. |

## Saved Outputs

`load_state` normally only reads a pickle. It can overwrite that same pickle in
these cases:

- legacy inline image arrays were stripped from old image tables;
- old batch-summary suffixes such as `_exp1` were migrated to `.exp1`;
- a legacy `<filename>.images.pkl` sidecar exists;
- paths were rebased and `resave_if_rebased=True`.

No figures, CSV tables, Excel workbooks, or pipeline run folders are created by
`load_state` itself. With the default `normalize_paths=True`, loading may
refresh derived save paths through `createSavePaths()`. For object types whose
`createSavePaths()` creates standard output directories, this can create
missing folders, but not analysis result files.

## Examples

### Load a batch and inspect it

```python
from PyFLASH import load_state

batch = load_state("outputs/pickles/scn_batch.pkl")
print(batch.name)
print(batch.summary.shape)
```

### Load without path normalization

```python
from PyFLASH import load_state

batch = load_state(
    "outputs/pickles/scn_batch.pkl",
    normalize_paths=False,
    verbose=False,
)
```

### Rebase moved paths and save the repaired pickle

```python
from PyFLASH import load_state

batch = load_state(
    "outputs/pickles/scn_batch.pkl",
    normalize_paths=True,
    resave_if_rebased=True,
)
```

## Notes

- `load_state` uses a PyFLASH-aware unpickler that remaps legacy
  `IF_analysis...` module paths to current `PyFLASH...` module paths.
- Path normalization checks the loaded object and nested experiments when the
  object has an `experiment_list`.
- `normalize_paths=True` can update the in-memory object without saving it. Use
  `resave_if_rebased=True` or call [`save_state`](save_state.md) if you want the
  repaired paths persisted.
- Because path normalization refreshes derived save paths, it can indirectly
  create standard output directories for object types whose `createSavePaths()`
  method creates folders.
- Individual plot or pipeline outputs are not regenerated when a pickle is
  loaded. The saved object just points to its output folders.

## See Also

- [Save state](save_state.md)
- [Normalize paths](normalize_paths.md)
- [Load and rebase a pickle](../workflows/load-and-rebase-a-pickle.md)
- [Pickle files](../outputs/pickle-files.md)
- [API reference](../api-reference.md)
