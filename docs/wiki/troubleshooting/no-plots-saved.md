# No Plots Saved

## Symptoms

- A figure renders in a notebook or UI preview, but no `.svg` appears in the
  folder.
- Re-running a plot finishes instantly without updating the existing file.
- Image plots land somewhere different from summary plots.
- A pipeline "completed" but its run folder looks empty.

## Likely Causes

- The call used `save=False`, which computes and returns results but writes no
  file. This is the intended preview mode.
- `Config.SAVE_MODE` is `False`, which disables figure writes globally at the
  shared `save_fig` layer.
- The output already exists and `Config.SKIP_EXISTING` (or a `skip_existing`
  argument) skipped the write.
- Figures are written under the object's figure folder, not next to your
  script. Standalone plots save under `batch.fig_path`; image plots save under
  `batch.image_fig_path`; pipelines save under a named run folder.
- The destination is not writable, or (on Windows) the path is very long.

## Fix

Save explicitly and look in the object's figure folder:

```python
from PyFLASH.plotting import plot_mean_bars

plot_mean_bars(batch, data_cols=["GFAP_Count"], save=True)
print(batch.fig_path)
```

If files still do not appear, confirm the global save switches:

```python
from PyFLASH import Config

print(Config.SAVE_MODE)      # must be True to write anything
print(Config.SKIP_EXISTING)  # True re-uses an existing file instead of rewriting
```

For pipelines, a reused `run_label` collides with an existing run folder. Choose
the collision policy with `if_exists` (`"overwrite"`, `"version"`, `"error"`, or
`"skip"`) rather than expecting old files to be replaced silently.

On Windows, a figure path longer than 245 characters emits a warning and is
written through an extended-length path, so it usually still saves. Shorten the
base path or set `Config.ALIASES` to keep names short. A genuine failure to
write is almost always a permission or read-only-folder problem on the target
directory.

## Check

List the most recent SVGs under the figure root:

```python
from pathlib import Path

root = Path(batch.fig_path)
print(sorted(root.rglob("*.svg"), key=lambda p: p.stat().st_mtime)[-10:])
```

For image plots, search `batch.image_fig_path` as well.

## Related Pages

- [Saving and run labels](../parameters/saving.md)
- [Figure folders](../outputs/figure-folders.md)
- [Pipeline run folders](../outputs/pipeline-run-folders.md)
- [Where results go](../getting-started/where-results-go.md)
- [Config object](../object-types/config.md)
