# Colocalisation And Composition Plots

## Use This When

Use composition plots when you want to show how marker objects divide into
categories. Use colocalisation plots when those categories are marker
intersections, nearest-neighbour flags, or contains relationships.

Pie and stacked-bar plots are best for compact summaries. UpSet plots are best
when several binary colocalisation indicators overlap. Sankey plots are best
when you want to show a conditional branch through several indicators.

## Input Data

These plots use marker-level data tables, usually `source.data[marker].df`.
They are not summary-table plots.

`plot_pie_charts` needs a marker table column, resolved from `marker` plus
`x_attr`, such as a region, categorical class, or thresholded numeric value.

`plot_combo_pies` needs precomputed combo-family columns for the selected
marker. Families include detailed and pooled Vol/CPC combo variants.

`plot_coloc_upset` and `plot_coloc_sankey` auto-detect binary colocalisation
indicator columns with names like:

```text
<marker>_ColocCount<other_marker>
<marker>_ClosestTo_<other_marker>
<marker>_Contains_<other_marker>
```

`remove_closest=True` excludes the closest-neighbour columns from that search.

## Main Functions

| Function | Registry name | Use |
|---|---|---|
| [`plot_pie_charts`](../functions/plot_pie_charts.md) | `pie_charts` | Plot categorical or threshold-binned marker attributes. |
| [`plot_combo_pies`](../functions/plot_combo_pies.md) | `combo_pies` | Plot mutually exclusive marker-combination signatures. |
| [`plot_coloc_upset`](../functions/plot_coloc_upset.md) | `coloc_upset` | Plot binary colocalisation intersections as an UpSet plot. |
| [`plot_coloc_sankey`](../functions/plot_coloc_sankey.md) | `coloc_sankey` | Plot colocalisation branches as a Plotly Sankey/alluvial figure. |

## Common Options

| Option | Meaning |
|---|---|
| `marker` | Source marker table. A list queues over markers for UpSet and Sankey. |
| `x_attr` | Marker attribute to count in `plot_pie_charts`. |
| `family` | Combo family used by `plot_combo_pies`. |
| `by` / `factor` | Group panels by condition, all data, or a factor column. |
| `filter_by` / `specificity` | Filter rows or run a queue of row filters. `filter_by` is preferred; `specificity` is the legacy alias. |
| `roi` | Queue over ROI bases when the source object supports them. |
| `plot_format` | `"pie"` or `"bar"` for pie/combo plots. |
| `show_counts`, `show_pct`, `include_N` | Control value labels and subject counts. |
| `include_neither` | Include all-false branches/intersections in UpSet or Sankey output. |
| `normalize` | Show percentages instead of raw counts in UpSet or Sankey output. |
| `order` | Reorder pie categories or Sankey indicator stages. |

## Outputs

Pie and combo functions return PyFLASH iterator dictionaries. Action-level
entries include labels, raw labels, counts, percentages, group name, and animal
count.

UpSet returns a Matplotlib figure for one combined panel, or a dictionary of
figures when grouped. It requires the optional `upsetplot` dependency.

Sankey returns a Plotly figure for one combined panel, or a dictionary of Plotly
figures when grouped. It requires `plotly`; saving uses static image export when
available and falls back to HTML.

## Examples

Plot region composition for one marker:

```python
from PyFLASH.plotting import plot_pie_charts

result = plot_pie_charts(
    batch,
    marker="GFAP",
    x_attr="Region",
    plot_format="bar",
    show_counts=True,
    save=False,
)
print(result["pie_counts"])
```

Plot marker-combination signatures:

```python
from PyFLASH.plotting import plot_combo_pies

plot_combo_pies(
    batch,
    marker="GFAP",
    family="VolComboAny",
    include_none=True,
    save=True,
)
```

Plot colocalisation intersections:

```python
from PyFLASH.plotting import plot_coloc_upset, plot_coloc_sankey

upset_fig = plot_coloc_upset(batch, marker="GFAP", by="conditions", save=False)
sankey_fig = plot_coloc_sankey(batch, marker="GFAP", include_neither=True, save=False)
```

## Interpretation

Pie slices and stacked bars show distributions within each plotted group, not
subject-level means. Use `include_N=True` to make the number of contributing
subjects visible when that context matters.

UpSet and Sankey plots coerce common binary encodings to true/false and treat
missing values as false. Check the detected column names when a plot looks
sparser than expected.

`include_neither=False` makes Sankey plots focus on the true branches. This is
useful for colocalised objects but hides the all-false population.

## See Also

- [Marker tables](../data-structures/marker-tables.md)
- [Filter By and row filters](../parameters/specificity.md)
- [Figure folders](../outputs/figure-folders.md)
- [Group comparison plots](group-comparison-plots.md)
- [Location and 3D plots](location-plots.md)
