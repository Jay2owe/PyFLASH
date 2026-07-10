# Axis Limit Helpers

## Summary

`set_axis_limits`, `clear_axis_limits`, and `lock_axis_limits` manage reusable
axis limits for plots that share measurements across panels or queued outputs.

They store a simple dictionary on the input object as `experiment.axis_limits`.
Plot functions that consult this registry use it only when explicit per-call
axis arguments such as `x_range`, `y_range`, `xmin`, `xmax`, `ymin`, or `ymax`
were not supplied.

## Signature

```python
set_axis_limits(experiment, mapping=None, **kwargs)

clear_axis_limits(experiment, columns=None)

lock_axis_limits(
    experiment,
    columns=None,
    *,
    source="summary",
    overwrite=False,
)
```

## Input Object Types

| Object type | Accepted? | Notes |
|---|---:|---|
| `Batch` | Yes | Stores `axis_limits` on the batch object. |
| `Experiment` | Yes | Stores `axis_limits` on the experiment object. |
| `MiniExperiment` | Yes | Works for summary-based plots when it exposes a `summary` table. |
| `DataFrameExperiment` | Yes | Works for summary-based plots and marker tables supplied through `data`. |
| `pandas.DataFrame` | No | The registry is stored as an attribute on a PyFLASH-like object, not on a bare table. |

## Parameters

| Parameter | Type | Default | Meaning |
|---|---|---:|---|
| `experiment` | PyFLASH object | required | Object that will receive or read the `axis_limits` dictionary. |
| `mapping` | `dict[str, tuple]` or `None` | `None` | Manual limits to store, as `{column_name: (low, high)}`. A `None` value clears that key. |
| `**kwargs` | `tuple` values | none | Shorthand manual limits, for example `set_axis_limits(batch, Period=(22, 26))`. |
| `columns` | `str`, list-like, or `None` | `None` | For `clear_axis_limits`, the keys to remove; `None` clears all. For `lock_axis_limits`, columns to compute; `None` scans candidate numeric columns. |
| `source` | `str` | `"summary"` | For `lock_axis_limits`, `"summary"` uses `experiment.summary`; any other value is treated as a marker key and uses `experiment.data[source].df`. |
| `overwrite` | `bool` | `False` | Preserve existing registry entries by default. Set `True` to replace them with newly computed bounds. |

Each limit value must be a two-item `(low, high)` pair. `low` or `high` can be
`None` to leave one side unpinned, but finite numeric values must be distinct.

## Returns

| Return value | Type | Meaning |
|---|---|---|
| `registry` | `dict` | Snapshot of the object's `axis_limits` dictionary after the update. Keys are column names and values are `(low, high)` tuples. |

## Saved Outputs

No files are written by these helpers. The stored registry is in memory only.
If the object is later saved with [`save_state`](save_state.md), the
`axis_limits` attribute is included in that pickle.

## Examples

### Set manual limits

```python
from PyFLASH import set_axis_limits
from PyFLASH.plotting import plot_regressions

set_axis_limits(batch, {"PeriodMean": (22.0, 26.0)})

plot_regressions(
    batch,
    x="Age",
    y="PeriodMean",
    normalize_x=False,
    normalize_y=False,
    save=False,
)
```

### Use keyword shorthand

```python
from PyFLASH import set_axis_limits

registry = set_axis_limits(
    batch,
    GFAP_VolumeTotal=(0, 1200),
    Iba1_VolumeTotal=(None, 900),
)

print(registry)
```

### Compute limits from the summary table

```python
from PyFLASH import lock_axis_limits

registry = lock_axis_limits(
    batch,
    columns=["GFAP Volume", "Iba1 Volume"],
    source="summary",
)
```

### Clear one column or everything

```python
from PyFLASH import clear_axis_limits

clear_axis_limits(batch, "GFAP Volume")
clear_axis_limits(batch)
```

### Lock limits from a marker table

```python
from PyFLASH import lock_axis_limits

lock_axis_limits(
    batch,
    columns=["Area", "Volume"],
    source="Cells",
    overwrite=True,
)
```

Here `source="Cells"` reads `batch.data["Cells"].df`.

## Notes

- Explicit plot arguments override stored limits.
- `set_axis_limits` creates `experiment.axis_limits` when it is missing.
- Passing `None` for a column limit removes that column from the registry.
- `lock_axis_limits` skips missing columns, empty columns, non-finite ranges,
  and columns with only one finite value.
- For `source="summary"`, computed ranges come from `experiment.summary`.
- For marker-table sources, `lock_axis_limits` raises `ValueError` when the
  marker key is unknown.
- Excluded sentinel values are treated as missing while auto-locking ranges.

## See Also

- [Saving parameters](../parameters/saving.md)
- [Regression plots](../plot-types/regression-plots.md)
- [Distribution plots](../plot-types/distribution-plots.md)
- [plot_regressions](plot_regressions.md)
- [plot_scatter_3d](plot_scatter_3d.md)
