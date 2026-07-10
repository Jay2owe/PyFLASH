# plot_condition_key

## Summary

`plot_condition_key` creates a standalone legend for PyFLASH condition colours
and styles. Use it when figures are assembled outside PyFLASH but still need a
key that matches PyFLASH bar, pie, radar, and regression styling.

Registry name: `condition_key`.

## Example figure

![plot_condition_key example figure](../gallery/images/plot_condition_key.svg)

*Standalone colour/style key for groups A/B/C. Rendered from the [synthetic example dataset](../examples/README.md).*

## Signature

```python
plot_condition_key(
    experiment,
    save=True,
    save_path=None,
    filename="condition_key",
    auto_style=True,
    style_cycle=None,
    ncol=1,
    title=None,
    dpi=200,
)
```

## Input Object Types

| Object type | Accepted? | Notes |
|---|---:|---|
| `Batch` | Yes | Uses `condition_list` and `fig_path`. |
| `Experiment` | Yes | Works when a group list is present. |
| `MiniExperiment` | Yes | Works when loaded into a PyFLASH-like object with conditions. |
| `pandas.DataFrame` | No | Raw tables do not carry condition style metadata. |

## Parameters

| Parameter | Type | Default | Meaning |
|---|---|---:|---|
| `experiment` | PyFLASH-like object | required | Object with a `condition_list`. |
| `save` | `bool` | `True` | Save the key to disk. When `False`, return the figure. |
| `save_path` | Path-like or `None` | `None` | Exact output path. Overrides `fig_path/filename.png`. |
| `filename` | `str` | `"condition_key"` | Base file name used when `save_path` is omitted. |
| `auto_style` | `bool` | `True` | Apply PyFLASH's style-collision rules for crossed designs. |
| `style_cycle` | list-like or `None` | `None` | Custom style cycle for groups sharing colours. |
| `ncol` | `int` | `1` | Number of legend columns. |
| `title` | `str` or `None` | `None` | Optional legend title. |
| `dpi` | `int` | `200` | DPI for saved PNG output. |

## Returns

| Return value | Type | Meaning |
|---|---|---|
| `path` | `str` | Returned when `save=True`. Path to the saved PNG. |
| `fig` | `matplotlib.figure.Figure` | Returned when `save=False`. |

## Saved Outputs

With `save=True`, the function saves a PNG. By default the path is:

```text
<experiment.fig_path>/condition_key.png
```

When `save_path` is provided, the figure is written exactly there.

## Examples

### Save the default key

```python
from PyFLASH.plotting import plot_condition_key

path = plot_condition_key(batch)
print(path)
```

### Return a figure for manual composition

```python
fig = plot_condition_key(
    batch,
    save=False,
    ncol=2,
    title="Groups",
)
```

### Save to a custom path

```python
plot_condition_key(
    batch,
    save=True,
    save_path="outputs/condition_key.png",
    dpi=300,
)
```

## Notes

- The function raises `ValueError` when no condition handles can be built.
- `auto_style=True` is useful for crossed designs where two groups share a
  colour but differ by hatch or fill style.
- Unlike most PyFLASH figure saves, this function writes a PNG directly with
  `fig.savefig()` rather than `save_fig()`.

## See Also

- [Groups and factors](../parameters/conditions-and-factors.md)
- [plot_radar](plot_radar.md)
- [plot_pie_charts](plot_pie_charts.md)
- [plot_mean_bars](plot_mean_bars.md)
