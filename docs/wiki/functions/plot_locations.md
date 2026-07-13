# plot_locations

## Summary

`plot_locations` draws marker object coordinates as spatial panels. It can show
raw object locations, merged marker panels, filtered extra panels, colocaliser
panels, optional image backgrounds, and ROI outlines.

Registry name: `locations`.

## Example figure

<!-- gallery-example-code:start -->
Gallery render call (after `ex = build_example_data(fig_path=TMP)`, `exp = ex.experiment`, and `P = PyFLASH.plotting`):

```python
import numpy as np
import pandas as pd
from PyFLASH import from_dataframe

r = np.random.default_rng(7)
n = 110
cluster = r.integers(0, 2, n)
x = np.where(cluster == 0, r.normal(180, 45, n), r.normal(330, 50, n))
y = np.where(cluster == 0, r.normal(300, 55, n), r.normal(520, 60, n))
marker_table = pd.DataFrame(
    {
        "AnimalName": ["A1"] * n,
        "Condition": ["A"] * n,
        "Region": ["ROIa1"] * n,
        "ROI": ["ROIa"] * n,
        "Marker1_XM": np.clip(x, 20, 480),
        "Marker1_YM": -np.clip(y, 20, 780),
        "Marker1_IntDen": np.clip(r.normal(100, 25, n), 0, None),
        "Marker1_Volume": np.clip(r.normal(12, 3, n), 1, None),
    }
)
summary = pd.DataFrame(
    {"AnimalName": ["A1"], "Condition": ["A"], "Marker1_Count": [float(n)]}
)
spatial_exp = from_dataframe(
    summary,
    group_col="Condition",
    subject_col="AnimalName",
    data={"Marker1": marker_table},
    fig_path=TMP,
)
P.plot_locations(
    spatial_exp,
    objects=["Marker1"],
    roi="ROIa",
    black_background=True,
    marker_colors={"Marker1": "#19e6ff"},
    save=True,
)
```
<!-- gallery-example-code:end -->

![plot_locations example figure](../gallery/images/plot_locations.svg)

*Spatial map of one subject's `Marker1` object locations (points-only mode). Rendered from the [synthetic example dataset](../examples/README.md).*

## Signature

```python
plot_locations(
    experiment,
    objects,
    separate_by="groups",
    join_by="subjects",
    merge=True,
    colocalise=True,
    annotate=True,
    extra_graphs=None,
    images=None,
    colocaliser=None,
    extra_graph_colors=None,
    image_layout="shared",
    draw_rois=None,
    hue=True,
    marker_colors=None,
    black_background=False,
    panel_line_width=2.0,
    dpi=100,
    save=True,
    fast_loading=False,
    preview_max_dim=None,
    image_adjustments=None,
    edit_mode=False,
    use_existing_edits=False,
    specificity=None,
    filter_by=None,
    roi=None,
    extra_graph=None,
    merge_extra_graphs=None,
    overlay_with_images=None,
    draw_roi=None,
    overlay_all_extra_graphs=None,
    _return_fig=False,
)
```

## Input Object Types

| Object type | Accepted? | Notes |
|---|---:|---|
| `Batch` | Yes | Main supported input. Needs marker tables, group metadata, summary, and region mappings. |
| `Experiment` | Yes | Works when marker coordinate tables and ROI metadata are available. |
| `MiniExperiment` | Usually no | Only works if converted data expose the same marker-coordinate structure. |
| `pandas.DataFrame` | No | A raw summary table does not carry marker data, region dictionaries, or image paths. |

## Parameters

| Parameter | Type | Default | Meaning |
|---|---|---:|---|
| `experiment` | `Batch` or `Experiment` | required | Source object with marker data and group metadata. |
| `objects` | marker spec | required | Marker panels to plot as object coordinates. Strings make one panel; tuples merge markers into one panel. |
| `separate_by` | `str` | `"groups"` | Outer figure grouping. Aliases: `"conditions"` for groups, `"animals"` for subjects. |
| `join_by` | `str` | `"subjects"` | Rows within a figure. Alias: `"animals"` for subjects. |
| `merge` | `bool` | `True` | Merge marker panels where marker specs request combined panels. |
| `colocalise` | `bool` | `True` | Preserve legacy colocalisation behaviour for object panels. |
| `annotate` | `bool` | `True` | Label panels with marker or overlay names. |
| `extra_graphs` | column spec or `None` | `None` | Extra boolean columns to render as filtered panels. Tuples overlay several filters in one panel. |
| `images` | marker spec or `None` | `None` | Image marker panels to draw as backgrounds or side-by-side panels. |
| `colocaliser` | `bool`, `str`, list, or `None` | `None` | Add panels using detected `<object>_Contains_<marker>` columns. |
| `extra_graph_colors` | colour spec or `None` | `None` | Colours for extra filtered panels. |
| `image_layout` | `str` | `"shared"` | Image/point panel layout. |
| `draw_rois` | `bool`, marker-panel spec, or `None` | `None` | Draw ROI outlines on matching image panels. |
| `hue` | `bool` | `True` | Colour points by `<marker>_IntDen` when available. |
| `marker_colors` | `dict` or `None` | `None` | Override marker colours. |
| `black_background` | `bool` | `False` | Use black figure and axes backgrounds. |
| `panel_line_width` | `float` | `2.0` | Width of panel separator spines. |
| `dpi` | `int` | `100` | Figure resolution. |
| `save` | `bool` | `True` | Save figures under the standard figure folder. |
| `fast_loading` | `bool` | `False` | Use preview loading for image overlays. |
| `preview_max_dim` | `int` or `None` | `None` | Downsample image overlay previews. |
| `image_adjustments` | `dict` or `None` | `None` | Per-marker brightness/contrast settings. |
| `edit_mode` | `bool` | `False` | Open the image-adjustment editor for image overlays. |
| `use_existing_edits` | `bool` | `False` | Reuse saved image adjustments. |
| `filter_by` | dict, tuple, list, or `None` | `None` | Row filter. Lists run queue mode. Alias: `specificity`. |
| `roi` | `str`, list-like, or `None` | `None` | ROI-base selector. Multiple ROI bases run queue mode. |

## Parameter Options

### `separate_by` options

| Option | Behavior |
|---|---|
| `"groups"` (default) | Create separate outer figures by group. Alias: `"conditions"`. |
| `"subjects"` | Create separate outer figures by subject. Alias: `"animals"`. |

### `join_by` options

| Option | Behavior |
|---|---|
| `"subjects"` (default) | Use subjects as rows within a figure. Alias: `"animals"`. |
| `"rois"` | Use ROIs as rows within a figure. |

### `image_layout` options

| Option | Behavior |
|---|---|
| `"shared"` (default) | Overlay points on image axes. |
| `"separate"` | Place images beside point panels. |

## Returns

| Return value | Type | Meaning |
|---|---|---|
| `result` | `dict` | Standard PyFLASH iterator result, usually accumulated action records. |
| `result` | `dict` | In ROI or row-filter queue mode, a dictionary keyed by ROI or filter value. |

The internal `_return_fig=True` path returns the Matplotlib figure used for UI
preview/edit mode. Normal user calls should use saved files or the iterator
result dictionary.

## Saved Outputs

With `save=True`, figures are saved under the `Locations` plot folder below
`experiment.fig_path`. Saved names include the outer group name, panel tag,
`join_by` value, row-filter suffix, and ROI suffix when relevant.

No tables are written by this function.

## Examples

### Plot one marker by group and subject

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

### Overlay coordinates on images

```python
plot_locations(
    batch,
    objects=["GFAP"],
    images=["DAPI"],
    image_layout="shared",
    draw_rois=True,
    fast_loading=True,
    preview_max_dim=1024,
    save=True,
)
```

### Add filtered colocalisation panels

```python
result = plot_locations(
    batch,
    objects=["Caspase3"],
    extra_graphs=["Caspase3_Contains_mCherry"],
    extra_graph_colors={"Caspase3_Contains_mCherry": "magenta"},
    save=False,
)

print(result)
```

## Notes

- Marker coordinate columns are resolved as `<marker>_XM` and `<marker>_YM`.
  Optional colour and size columns are `<marker>_IntDen` and `<marker>_Volume`.
- `images` requires imported image metadata. Without it, keep `images=None`.
- `draw_rois=True` only draws outlines where ROI coordinate or bounds metadata
  can be matched to the panel.
- `image_layout="shared"` cannot use more image panels than object panels.
- `extra_graph` and `draw_roi` are legacy aliases for `extra_graphs` and
  `draw_rois`.

## See Also

- [Location and 3D plots](../plot-types/location-plots.md)
- [ROI tables](../data-structures/roi-tables.md)
- [Image table](../data-structures/image-table.md)
- [plot_images](plot_images.md)
- [ROI selection](../parameters/roi.md)
