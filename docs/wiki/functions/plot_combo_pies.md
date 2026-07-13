# plot_combo_pies

## Summary

`plot_combo_pies` counts mutually exclusive marker-combination signatures and
displays them as pies or a combined stacked bar chart. Use it for precomputed
Vol/CPC combo-family columns when each object belongs to one combination
category.

Registry name: `combo_pies`.

## Example figure

<!-- gallery-example-code:start -->
Gallery render call (after `ex = build_example_data(fig_path=TMP)`, `exp = ex.experiment`, and `P = PyFLASH.plotting`):

```python
P.plot_combo_pies(exp, marker="Marker1", family="comboany", save=True)
```
<!-- gallery-example-code:end -->

![plot_combo_pies example figure](../gallery/images/plot_combo_pies.svg)

*`Marker1` colocalisation-combo composition (group C). Rendered from the [synthetic example dataset](../examples/README.md).*

## Signature

```python
plot_combo_pies(
    experiment,
    marker,
    family="comboany",
    by="conditions",
    factor=None,
    start_angle=90,
    line_width=1.0,
    save=True,
    specificity=None,
    filter_by=None,
    roi=None,
    plot_format="pie",
    show_counts=None,
    show_pct=None,
    labels=None,
    order=None,
    include_none=True,
    collapse_markers=None,
    include_N=False,
    as_counts=None,
    include_n=None,
    bottom_ticks=False,
    bottom_tick_labels=False,
    auto_style=None,
    style_cycle=None,
)
```

## Input Object Types

| Object type | Accepted? | Notes |
|---|---:|---|
| `Batch` | Yes | Main supported input. Reads `experiment.data[marker].df`. |
| `Experiment` | Yes | Works when marker combo-family columns are present. |
| `MiniExperiment` | Sometimes | Works only if marker combo columns exist in a compatible marker table. |
| `pandas.DataFrame` | No | This wrapper does not accept raw tables directly. |

## Parameters

| Parameter | Type | Default | Meaning |
|---|---|---:|---|
| `experiment` | PyFLASH-like object | required | Source object with marker data and figure paths. |
| `marker` | `str` or list-like | required | Marker table to inspect. List-like values queue all markers. |
| `family` | `str` or list-like | `"comboany"` | Combo family to count. List-like values queue all families. |
| `by` | `str` | `"conditions"` | Grouping mode when `factor` is not set. |
| `factor` | `str` or `None` | `None` | Factor column to group by instead of full condition. |
| `start_angle` | number | `90` | Pie starting angle. |
| `line_width` | number | `1.0` | Wedge or stacked-bar edge width. Must be non-negative. |
| `save` | `bool` | `True` | Save figures under `experiment.fig_path`. |
| `filter_by` | dict, tuple, list, or `None` | `None` | Row filter. Lists run queue mode. Alias: `specificity`. |
| `roi` | `str`, list-like, or `None` | `None` | ROI-base selector. Multiple ROI bases run queue mode. |
| `plot_format` | `str` | `"pie"` | Plot layout. |
| `show_counts` | `bool` or `None` | `None` | Show raw counts in labels. Alias: `as_counts`. |
| `show_pct` | `bool` or `None` | `None` | Show percentages in labels. |
| `labels` | `dict` or `None` | `None` | Map combo signatures to display labels. |
| `order` | list-like or `None` | `None` | Category order for slices or stacks. |
| `include_none` | `bool` | `True` | Keep explicit `None` combo category when present. |
| `collapse_markers` | `str`, list-like, or `None` | `None` | Ignore selected partner markers and re-aggregate signatures before plotting. |
| `include_N` | `bool` | `False` | Add unique `AnimalName` count to labels. Alias: `include_n`. |
| `bottom_ticks`, `bottom_tick_labels` | `bool` | `False` | Tick visibility in stacked-bar mode. |
| `auto_style`, `style_cycle` | style controls | `None`, `None` | Apply hatch/fill styles for groups sharing colours. `None` uses the active style default. |

## Parameter Options

### `plot_format` options

| Option | Behavior |
|---|---|
| `"pie"` (default) | Draw one pie chart per group. |
| `"bar"` | Draw one combined stacked bar chart across groups. |

## Returns

| Return value | Type | Meaning |
|---|---|---|
| `result` | `dict` | Standard PyFLASH iterator result. Includes labels, counts, percentages, group, and subject count. |
| `result` | `dict` | Queue mode returns dictionaries keyed by ROI, row filter, or `(marker, family)` tuple. |

## Saved Outputs

With `save=True`, output goes under a `ComboPies` plot folder. Pie mode saves one
figure per group. Bar mode saves one combined stacked-bar figure. Saved names
include the marker, combo-family prefix, unit tag, optional collapse suffix,
row-filter suffix, and ROI suffix.

No tables are written.

## Examples

### Plot the default pooled combo family

```python
from PyFLASH.plotting import plot_combo_pies

result = plot_combo_pies(
    batch,
    marker="GFAP",
    family="VolComboAny",
    save=False,
)

print(result["pie_counts"])
```

### Use a stacked bar view

```python
plot_combo_pies(
    batch,
    marker="GFAP",
    family="CPCCombo",
    plot_format="bar",
    show_pct=True,
    include_N=True,
    save=True,
)
```

### Collapse a partner marker before plotting

```python
plot_combo_pies(
    batch,
    marker="GFAP",
    family="VolCombo",
    collapse_markers=["DAPI"],
    labels={"None": "No partner marker"},
    save=False,
)
```

## Notes

- Supported family names are normalized internally, so legacy casing such as
  `"VolComboAny"` is accepted.
- The function raises `ValueError` when no matching combo-family columns are
  found for the marker.
- Combo categories are mutually exclusive after signature construction.
- `include_none=False` removes explicit none/no-partner categories when present.
- The plot is describe-layer exempt because it reports descriptive
  proportions, not a statistical comparison.

## See Also

- [Colocalisation and composition plots](../plot-types/colocalisation-plots.md)
- [Marker tables](../data-structures/marker-tables.md)
- [plot_pie_charts](plot_pie_charts.md)
- [plot_coloc_sankey](plot_coloc_sankey.md)
