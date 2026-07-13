# create_batch

## Summary

`create_batch` creates a processed `Batch` from one or more FLASH/ImageJ
experiment folders, or loads a previously saved batch from a pickle cache.

Use it at the start of most analyses.

## Signature

```python
create_batch(
    name,
    conditions,
    batch_path,
    experiments=None,
    threshold=None,
    pickle_path=None,
    rerun=False,
    import_images=True,
    reimport_images=False,
    progress=True,
)
```

## Input Object Types

| Object type | Accepted? | Notes |
|---|---:|---|
| `groupList` | Yes | Required by the current signature as `conditions`. Alias object name: `conditionList`. Build it with `GroupBuilder`; `ConditionBuilder` remains a legacy builder name. |
| Path-like folder | Yes | Used for `batch_path`, `pickle_path`, and experiment paths. |
| `Experiment` list | Yes | Pass as `experiments` when experiments are already constructed. |
| `pandas.DataFrame` | No | `create_batch` imports experiment folders; it does not create a batch directly from a table. |

## Parameters

| Parameter | Type | Default | Meaning |
|---|---|---:|---|
| `name` | `str` | required | Batch name. Also used as the pickle filename when `pickle_path` is set. |
| `conditions` | `groupList` | required | Experimental groups, labels, colors, factors, and comparisons. The parameter name is retained by the current `create_batch` signature; `conditionList` is accepted as the legacy object name. |
| `batch_path` | Path-like | required | Output folder for the batch. Also used for experiment discovery when `experiments=None`. |
| `experiments` | `dict`, `list`, path-like, or `None` | `None` | Source experiments. A dict maps experiment names to paths; a list contains prebuilt experiments; a folder is scanned; `None` scans `batch_path`. |
| `threshold` | `int` or `None` | `None` | Colocalisation threshold. `None` uses `Config.THRESHOLD`. |
| `pickle_path` | Path-like or `None` | `None` | Folder for saved pickle cache files. |
| `rerun` | `bool` | `False` | If `False`, return an existing pickle when available. If `True`, reprocess from source data. |
| `import_images` | `bool` | `True` | Import image paths and metadata during processing. |
| `reimport_images` | `bool` | `False` | When `rerun=True`, force image import even if `import_images=False`. |
| `progress` | `bool` | `True` | Show progress output while creating and processing the batch. |

## Returns

| Return value | Type | Meaning |
|---|---|---|
| `batch` | `Batch` | Processed batch with `summary`, `condition_list`, `fig_path`, experiments, aliases, and export methods. |

## Saved Outputs

`create_batch` itself returns the in-memory `Batch`. When `pickle_path` is set,
it can also load from or later save to `<pickle_path>/<name>.pkl` through the
batch workflow.

The returned batch writes plots and analysis outputs under `batch.fig_path`.

## Examples

### Basic batch creation

```python
from PyFLASH import GroupBuilder, create_batch

groups = (
    GroupBuilder("Diagnosis")
    .add("Control", short="Control", color="blue")
    .add("MCI", short="MCI", color="orange")
    .add("AD", short="AD", color="red")
    .compare("Control", "MCI")
    .compare("Control", "AD")
    .build()
)

batch = create_batch(
    "SCN_Diagnosis",
    groups,
    batch_path=r"C:\path\to\batch-output",
    experiments={
        "Cohort_1": r"C:\path\to\Cohort_1",
        "Cohort_2": r"C:\path\to\Cohort_2",
    },
    pickle_path=r"C:\path\to\pickles",
)
```

### Force a rebuild

```python
batch = create_batch(
    "SCN_Diagnosis",
    groups,
    batch_path=r"C:\path\to\batch-output",
    experiments=r"C:\path\to\experiment-parent",
    pickle_path=r"C:\path\to\pickles",
    rerun=True,
)
```

### Skip image import for faster table-only work

```python
batch = create_batch(
    "SCN_Diagnosis",
    groups,
    batch_path=r"C:\path\to\batch-output",
    experiments=r"C:\path\to\experiment-parent",
    import_images=False,
)
```

## Notes

- If a matching pickle exists and `rerun=False`, the function returns the cached
  batch instead of reprocessing folders.
- If `experiments` is a folder, PyFLASH scans immediate subfolders and keeps the
  ones that look like experiment folders.
- `threshold=None` means "use the project default", not "disable thresholding".
- Use `rerun=True` after changing source data, import settings, or condition
  definitions.

## See Also

- [Object model](../object-model.md)
- `save_state`
- `load_state`
- `GroupBuilder`
