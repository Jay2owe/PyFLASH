# Load And Rebase A Pickle

## Goal

Open a saved PyFLASH object without reprocessing source folders, and repair
stale paths when the pickle was moved between folders, machines, or user
accounts.

## Inputs

- A PyFLASH `.pkl` created by `create_batch(..., pickle_path=...)` or
  [`save_state`](../functions/save_state.md).
- Access to the same source/output folders, or equivalent folders that PyFLASH
  can resolve on the current machine.
- Optional choice about whether to persist any repaired paths back into the
  pickle.

## Minimal Path

```python
from PyFLASH import load_state

batch = load_state(r"C:\path\to\pickles\SCN_Diagnosis.pkl")

print(batch.name)
print(batch.summary.shape)
print(batch.fig_path)
```

## Full Workflow

1. Load normally first. `load_state` defaults to `normalize_paths=True`, so it
   checks path attributes while opening the object.

```python
from PyFLASH import load_state

batch = load_state(
    r"C:\path\to\pickles\SCN_Diagnosis.pkl",
    normalize_paths=True,
)
```

2. Inspect the loaded object:

```python
print(batch.name)
print(batch._state_path)
print(batch.fig_path)
print(batch.export_path)
print(batch.summary.head())
```

3. If you want repaired paths saved into the same pickle, load with
   `resave_if_rebased=True`:

```python
batch = load_state(
    r"C:\path\to\pickles\SCN_Diagnosis.pkl",
    normalize_paths=True,
    resave_if_rebased=True,
)
```

4. To control the save yourself, load without normalization, then call
   `normalize_paths` and `save_state`:

```python
from PyFLASH import load_state, normalize_paths, save_state

pickle_path = r"C:\path\to\pickles\SCN_Diagnosis.pkl"
batch = load_state(pickle_path, normalize_paths=False)

changed = normalize_paths(batch)
if changed:
    save_state(batch, pickle_path)
```

5. Continue plotting or exporting from the loaded object:

```python
from PyFLASH.plotting import plot_mean_bars

plot_mean_bars(
    batch,
    data_cols=["GFAP Volume"],
    save=False,
)
```

## Outputs

`load_state` returns the saved object in Python, usually a `Batch`. It records
the load path on `obj._state_path`.

`normalize_paths` changes the object in memory and returns `True` only when at
least one root path changed. It does not write files.

`save_state` writes a `.pkl` file when you choose to persist the repaired
object. Loading a pickle does not regenerate figures, CSV files, Excel
workbooks, or pipeline runs.

## Troubleshooting

- Paths still point to the old machine: confirm the current machine can see an
  equivalent folder. If the source/output folder is unavailable, PyFLASH leaves
  the old path in place.
- A loaded pickle has no images: modern pickles strip heavy image caches. Reopen
  source folders or rebuild/import images when needed.
- You changed source data: loading a pickle will not reprocess it. Re-run
  [`create_batch`](../functions/create_batch.md) with `rerun=True`.
- A legacy `IF_analysis...` pickle loads oddly: `load_state` remaps old module
  paths to current `PyFLASH...` names where possible.
- Output folders do not exist yet: path attributes can be set before folders
  are created. Plotting, exporting, or saving normally creates the needed
  destination folder.

## Next Steps

- [Plot from Python](plot-from-python.md)
- [Export Excel workbooks](export-excel-workbooks.md)
- [load_state reference](../functions/load_state.md)
- [normalize_paths reference](../functions/normalize_paths.md)
- [save_state reference](../functions/save_state.md)
- [Pickle files](../outputs/pickle-files.md)
- [Moved pickles troubleshooting](../troubleshooting/moved-pickles.md)
