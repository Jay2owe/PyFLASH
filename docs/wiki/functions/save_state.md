# save_state

## Summary

`save_state` writes a PyFLASH object to a pickle file. Use it to keep a
processed `Batch`, `Experiment`, `MiniExperiment`, or `DataFrameExperiment`
between Python sessions without re-importing or rebuilding it.

The function records the destination path on the object as `_state_path`,
creates the destination folder when needed, writes one `.pkl` file, and removes
the old sidecar image-cache file if it exists.

## Signature

```python
save_state(obj, filename=None, verbose=True)
```

## Input Object Types

| Object type | Accepted? | Notes |
|---|---:|---|
| `Batch` | Yes | Main supported object for full workflows. |
| `Experiment` | Yes | Saves the imported experiment object and its current summaries, metadata, and output paths. |
| `MiniExperiment` | Yes | Works when the object is picklable and has a usable `name`; `filename=None` also needs `csv_path`. |
| `DataFrameExperiment` | Yes, with explicit `filename` | Saves the adapted table object, including inferred or supplied groups and paths. Current `DataFrameExperiment` objects do not expose `csv_path`, so `save_state(df_exp)` without `filename` fails. |
| `pandas.DataFrame` | No | Pickling a bare table is not the public PyFLASH state format. Use pandas IO or wrap it with [`from_dataframe`](from_dataframe.md). |

## Parameters

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `obj` | PyFLASH object | required | Object to pickle. Public use is intended for `Batch`, `Experiment`, `MiniExperiment`, and `DataFrameExperiment`. |
| `filename` | Path-like or `None` | `None` | Destination pickle path. If omitted, PyFLASH uses `obj.csv_path / f"{obj.name}.pkl"`, so the object must expose `csv_path`. |
| `verbose` | `bool` | `True` | Print a confirmation message with object name, path, and file size. |

## Returns

| Return value | Type | Meaning |
|---|---|---|
| `None` | `None` | The function writes the pickle and mutates `obj._state_path`; it does not return the object. |

## Saved Outputs

`save_state` writes exactly one pickle file:

```text
<filename>
```

When `filename` has no parent folder, the file is written in the current working
directory. When the parent folder does not exist, PyFLASH creates it.

If an obsolete `<filename>.images.pkl` sidecar is present, `save_state` removes
it after writing the modern pickle.

## Examples

### Save to an explicit path

```python
from PyFLASH import save_state, load_state

save_state(batch, "outputs/pickles/scn_batch.pkl")
loaded = load_state("outputs/pickles/scn_batch.pkl")
```

### Save beside the object's CSV output folder

```python
from PyFLASH import save_state

# Requires batch.csv_path and batch.name to be set.
save_state(batch)
```

### Reuse the recorded path

```python
from PyFLASH import save_state

save_state(batch, "outputs/pickles/scn_batch.pkl", verbose=False)
print(batch._state_path)
```

## Notes

- The pickle stores Python object state, not a portable table export. Use Excel,
  CSV, or pipeline outputs when collaborators need non-Python files.
- Objects loaded with [`load_state`](load_state.md) can be saved again with
  `save_state`.
- `filename=None` is convenient for classic imported objects that have
  `csv_path`, but explicit filenames are clearer in scripts and UI workflows.
  Use an explicit filename for `DataFrameExperiment` objects.
- Moving a pickle between machines can leave absolute paths stale. Load it with
  path normalization, or call [`normalize_paths`](normalize_paths.md) after
  loading.

## See Also

- [Load state](load_state.md)
- [Normalize paths](normalize_paths.md)
- [Pickle files](../outputs/pickle-files.md)
- [API reference](../api-reference.md)
