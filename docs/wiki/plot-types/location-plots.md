# Location And 3D Plots

## Use This When

Use location plots when you need to see where detected objects sit inside an
ROI or on top of a microscopy image. Use 3D scatter plots when you need to
compare three summary measurements at subject level.

Location plots are spatial quality-control and spatial-pattern plots. 3D scatter
plots are exploratory summary plots.

## Input Data

`plot_locations` needs marker-level object tables with coordinate columns such
as `<marker>_XM` and `<marker>_YM`. Point colour and size can also use
`<marker>_IntDen` and `<marker>_Volume` when those columns exist. ROI-aware
layouts use the object's region dictionary and ROI metadata.

If image overlays are requested, the input object also needs an image table with
matching image paths. ROI outlines require ROI coordinate or bounds metadata.

`plot_scatter_3d` uses the summary table and needs three numeric summary
columns. It supports ROI-base selection when the input object exposes
`summaries`.

## Main Functions

| Function | Registry name | Use |
|---|---|---|
| [`plot_locations`](../functions/plot_locations.md) | `locations` | Draw object coordinate panels, optional filtered overlays, image backgrounds, and ROI outlines. |
| [`plot_scatter_3d`](../functions/plot_scatter_3d.md) | `scatter_3d` | Draw 3D scatter plots from three summary columns. |

## Common Options

| Option | Meaning |
|---|---|
| `objects` | Marker or marker panels to plot as spatial points. |
| `images` | Marker image panels to use as image backgrounds. |
| `extra_graphs` | Boolean marker columns to plot as extra filtered object panels. |
| `colocaliser` | Adds panels based on detected `_Contains_` columns. |
| `separate_by`, `join_by` | Control location panel grouping, usually groups by subjects or ROIs. |
| `image_layout` | `"shared"` overlays points on images; `"separate"` puts images beside point panels. |
| `filter_by` / `specificity`, `roi` | Queue or filter location and 3D plots by row metadata or ROI base. `filter_by` is preferred; `specificity` is the legacy alias. |
| `x_range`, `y_range`, `z_range` | Manual 3D axis limits. |
| `size_by` | Scale 3D points by another numeric summary column. |

## Outputs

`plot_locations` returns the standard PyFLASH iterator result dictionary. With
the internal `_return_fig=True` option it can return a figure, but normal user
calls should use the saved files.

`plot_scatter_3d` returns a dictionary of accumulated action results. The
dictionary includes plotted groups and axes where data were available. Queue
modes return dictionaries keyed by ROI, row filter, or `(x, y, z)` tuple.

With `save=True`, location figures are saved under a `Locations` plot folder and
3D scatter figures under a `Scatter3D` plot folder.

## Examples

Plot object locations by group and subject:

```python
from PyFLASH.plotting import plot_locations

plot_locations(
    batch,
    objects=["GFAP"],
    separate_by="groups",
    join_by="subjects",
    save=True,
)
```

Overlay object coordinates on matching marker images:

```python
plot_locations(
    batch,
    objects=["GFAP"],
    images=["DAPI"],
    image_layout="shared",
    draw_rois=True,
    save=True,
)
```

Make a 3D summary plot:

```python
from PyFLASH.plotting import plot_scatter_3d

result = plot_scatter_3d(
    batch,
    x="GFAP_Count",
    y="Iba1_Count",
    z="DAPI_Volume",
    combine=True,
    save=False,
)
print(result["group"])
```

## Interpretation

For location plots, first check that the correct coordinate suffixes and ROI
labels are being used. A blank panel usually means the marker table had no
matching rows after group, subject, ROI, or row-filter filtering.

For image overlays, verify image and coordinate alignment before interpreting
cell positions. ROI outlines are best-effort and depend on the available ROI zip
metadata.

For 3D scatter plots, shared axis limits make queued column combinations easier
to compare. Normalization changes the numerical scale, so keep normalized and
raw 3D plots separate in figure legends.

## See Also

- [ROI tables](../data-structures/roi-tables.md)
- [Image table](../data-structures/image-table.md)
- [Marker tables](../data-structures/marker-tables.md)
- [ROI selection](../parameters/roi.md)
- [Image panels](image-panels.md)
