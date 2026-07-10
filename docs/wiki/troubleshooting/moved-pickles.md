# Moved Pickles

## Symptoms

- A loaded `Batch` or `Experiment` still holds old drive letters, usernames, or
  Dropbox paths from another machine.
- Ordinary summary plots work, but image plots cannot find their `ImagePath`
  files.
- New figures are written beside the old project instead of the current one.

## Likely Causes

- The `.pkl` was created on a different machine, user account, or before the
  project folder moved. This is common when a repo is shared over Dropbox and
  edited from more than one computer.
- The pickle was copied without its neighbouring `Results/`, `Images/`, and
  experiment folders, so there is no equivalent path to rebase onto.
- `normalize_paths` can only rebase a root when an equivalent directory actually
  exists on the current machine. If the data is not present, the old path is
  left in place unchanged.

## Fix

`load_state` normalizes paths by default, so most moves are handled on load:

```python
from PyFLASH import load_state

batch = load_state("path/to/experiment/batch.pkl")
```

If the object is already in memory, rebase it in place. `normalize_paths`
updates `filePath` when it can resolve an equivalent existing directory,
refreshes the derived save-path attributes through `createSavePaths()`, and
returns whether anything changed:

```python
from PyFLASH import normalize_paths, save_state

changed = normalize_paths(batch)      # recurses into batch.experiment_list too
if changed:
    save_state(batch, "path/to/experiment/batch.pkl")
```

To rebase and persist in one step, reload with `resave_if_rebased=True`:

```python
batch = load_state("path/to/experiment/batch.pkl", resave_if_rebased=True)
```

`normalize_paths` repairs paths only. It does not reload source data or rerun
processing. If the images themselves moved, restore the experiment folder layout
(or rebuild the batch) before re-running image plots.

## Check

Inspect the rebased roots before a long run:

```python
from pathlib import Path

print(batch.filePath, batch.fig_path, batch.image_fig_path)

images = getattr(batch, "images", None)
if images is not None and "ImagePath" in images:
    print(images["ImagePath"].map(lambda p: Path(p).exists()).value_counts())
```

If most `ImagePath` values report `False`, fix the image folder layout before
plotting images.

## Related Pages

- [normalize_paths](../functions/normalize_paths.md)
- [load_state](../functions/load_state.md)
- [Load and rebase a pickle](../workflows/load-and-rebase-a-pickle.md)
- [Pickle files](../outputs/pickle-files.md)
- [Image table](../data-structures/image-table.md)
