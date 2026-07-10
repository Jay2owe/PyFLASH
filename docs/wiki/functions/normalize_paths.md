# normalize_paths

## Summary

`normalize_paths` repairs stale root paths on an object that is already loaded
in memory. It is useful after moving a saved PyFLASH pickle between computers,
user folders, or mounted drives.

The helper updates `filePath` values in place when PyFLASH can resolve an
equivalent existing directory, refreshes derived save-path attributes through
`createSavePaths()`, and returns whether any root path changed.

## Signature

```python
normalize_paths(obj, verbose=True)
```

## Input Object Types

| Object type | Accepted? | Notes |
|---|---:|---|
| `Batch` | Yes | Normalizes the batch and every object in `batch.experiment_list`. |
| `Experiment` | Yes | Normalizes `experiment.filePath` and refreshes derived output paths. |
| `MiniExperiment` | Yes | Works when it exposes `filePath` and `createSavePaths()`. |
| `DataFrameExperiment` | Limited | Usually already uses current explicit paths; works only for attributes present on the object. |
| `pandas.DataFrame` | No | A table has no PyFLASH `filePath` or save-path attributes. |

## Parameters

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `obj` | PyFLASH object | required | Loaded object whose path attributes should be checked. |
| `verbose` | `bool` | `True` | Print a status line for each root path that is rebased and warnings for path-refresh failures. |

## Returns

| Return value | Type | Meaning |
|---|---|---|
| `changed` | `bool` | `True` if any `filePath` value was changed; `False` otherwise. |

## Saved Outputs

No files are written by `normalize_paths`.

The object is changed in memory. To persist the repaired paths, call
[`save_state`](save_state.md) after normalization, or load with
`load_state(..., resave_if_rebased=True)`.

## Examples

### Rebase an already loaded batch

```python
from PyFLASH import load_state, normalize_paths, save_state

batch = load_state("outputs/pickles/scn_batch.pkl", normalize_paths=False)
changed = normalize_paths(batch)

if changed:
    save_state(batch, "outputs/pickles/scn_batch.pkl")
```

### Check without noisy output

```python
from PyFLASH import normalize_paths

changed = normalize_paths(batch, verbose=False)
print(changed)
```

### Prefer automatic rebasing during load

```python
from PyFLASH import load_state

batch = load_state(
    "outputs/pickles/scn_batch.pkl",
    normalize_paths=True,
    resave_if_rebased=True,
)
```

## Notes

- The helper only changes root paths when an equivalent existing path can be
  resolved. If the data is unavailable on the current machine, the old path is
  left in place.
- A `Batch` is normalized recursively: the batch object is checked first, then
  each nested experiment in `experiment_list`.
- Refreshing save paths depends on the object's `createSavePaths()` method. In
  current PyFLASH objects, that method updates path attributes without forcing
  unrelated analysis outputs to be created.
- `normalize_paths` does not reload source data or rerun processing. It only
  repairs paths on an existing object.

## See Also

- [Load state](load_state.md)
- [Save state](save_state.md)
- [Load and rebase a pickle](../workflows/load-and-rebase-a-pickle.md)
- [Moved pickles troubleshooting](../troubleshooting/moved-pickles.md)
- [API reference](../api-reference.md)
