# plot_images

## Summary

`plot_images` draws a grid of imported microscopy images from a `Batch` or
`Experiment` image table. Use it to browse source images, make quick marker/ROI
panels, add merged marker panels, draw ROI outlines, or save image QC figures.

Registry name: `images`.

## Signature

```python
plot_images(
    experiment,
    markers=None,
    animal_filter=None,
    subject_filter=None,
    roi_filter=None,
    save=True,
    ncols=None,
    max_images=None,
    tile_size=4.0,
    title=None,
    show=True,
    verbose=True,
    tile_gap=0.0,
    tile_gap_units="points",
    image_backend="auto",
    merge=False,
    merge_label="Merge",
    draw_rois=None,
    scale_bar=False,
    scale_bar_location="bottom left",
    scale_bar_size=None,
    scale_bar_units="microns",
    image_width_microns=None,
    pixel_size=None,
    fast_loading=False,
    preview_max_dim=None,
    image_adjustments=None,
    edit_mode=False,
    use_existing_edits=False,
    image_workers=None,
    progress=True,
    _preview_single_image=False,
)
```

## Input Object Types

| Object type | Accepted? | Notes |
|---|---:|---|
| `Batch` | Yes | Main supported input when images were imported. Uses `getImageTable()` or `.images`. |
| `Experiment` | Yes | Uses the experiment image table and image figure folder. |
| `MiniExperiment` | Usually no | Only works if the object has compatible image-table attributes. Flat CSV data are not enough. |
| `pandas.DataFrame` | No | The function needs image paths plus save-path methods, not just summary rows. |

## Parameters

| Parameter | Type | Default | Meaning |
|---|---|---:|---|
| `experiment` | `Batch` or `Experiment` | required | Source object with an image table. |
| `markers` | `str`, list-like, or `None` | `None` | Marker image names to show. `None` uses available markers. |
| `subject_filter` | `str`, list-like, or `None` | `None` | Preferred subject filter. Matches `AnimalName` by string. |
| `animal_filter` | `str`, list-like, or `None` | `None` | Legacy alias for `subject_filter`. |
| `roi_filter` | `str`, list-like, or `None` | `None` | Filter image rows by `ROI`. |
| `save` | `bool` | `True` | Save the figure under the object's image figure folder. |
| `ncols` | `int` or `None` | `None` | Number of grid columns. `None` chooses a square-ish layout. |
| `max_images` | `int` or `None` | `None` | Limit image rows before plotting. Ignored for merged marker-panel layout. |
| `tile_size` | `float` | `4.0` | Tile height in inches. Width follows image aspect ratio. |
| `title` | `str` or `None` | `None` | Custom figure title. |
| `show` | `bool` | `True` | Keep the figure open for interactive display. `False` closes it after creation. |
| `verbose` | `bool` | `True` | Print save messages. |
| `tile_gap` | `float` | `0.0` | Gap between tiles. |
| `tile_gap_units` | `str` | `"points"` | Gap units. Accepted values: `"points"` or `"inches"`. |
| `image_backend` | `str` | `"auto"` | Image reader. Accepted values: `"auto"`, `"tifffile"`, `"cv2"`, `"imageio"`, `"pil"`. |
| `merge` | `bool` | `False` | Include merged marker panels when several markers are requested. |
| `merge_label` | `str` | `"Merge"` | Label for merged marker panels. |
| `draw_rois` | `bool`, marker-panel spec, or `None` | `None` | Draw ROI outlines on matching image panels. |
| `scale_bar` | `bool` | `False` | Add scale bars to tiles. |
| `scale_bar_location` | `str` | `"bottom left"` | Scale-bar corner. |
| `scale_bar_size` | number or `None` | `None` | Explicit scale-bar length. Auto-selects a reasonable length when omitted. |
| `scale_bar_units` | `str` | `"microns"` | `"microns"` or `"pixels"`. |
| `image_width_microns` | number or `None` | `None` | Known image width used to compute micron scale. |
| `pixel_size` | number or `None` | `None` | Microns per pixel. Overrides package default pixel size. |
| `fast_loading` | `bool` | `False` | Use preview-sized loading when no explicit preview size is supplied. |
| `preview_max_dim` | `int` or `None` | `None` | Downsample images so the longest side is no larger than this many pixels. |
| `image_adjustments` | `dict` or `None` | `None` | Per-marker brightness/contrast settings. |
| `edit_mode` | `bool` | `False` | Open the interactive image-adjustment editor. |
| `use_existing_edits` | `bool` | `False` | Reuse saved image edits for the same marker/filter context. |
| `image_workers` | `int`, `"auto"`, or `None` | `None` | Parallel image-loading workers. |
| `progress` | `bool` | `True` | Show progress for prepare, filter, load, render, and save steps. |

## Returns

| Return value | Type | Meaning |
|---|---|---|
| `fig` | `matplotlib.figure.Figure` | Image grid figure. Returned even when `show=False`. |

The returned figure has useful attributes:

| Attribute | Meaning |
|---|---|
| `fig.PyFLASH_image_df` | Filtered image table used for the plot. |
| `fig.PyFLASH_save_path` | Saved figure path, or `None` when `save=False`. |
| `fig.PyFLASH_image_adjustments` | Effective brightness/contrast settings used. |

## Saved Outputs

With `save=True`, the function creates save paths if needed and writes one
figure under `experiment.image_fig_path`. The file name is derived from the
filtered image table and includes `"merged"` when `merge=True`.

No image files are copied by `plot_images`; it reads from `ImagePath`.

## Examples

### Browse one marker without writing files

```python
from PyFLASH.plotting import plot_images

fig = plot_images(
    batch,
    markers=["DAPI"],
    subject_filter="Mouse_01",
    save=False,
    show=False,
)

print(fig.PyFLASH_image_df[["AnimalName", "Marker", "ROI"]])
```

### Save a merged marker panel with ROI outlines

```python
plot_images(
    batch,
    markers=["DAPI", "GFAP"],
    merge=True,
    draw_rois=True,
    scale_bar=True,
    save=True,
)
```

### Speed up a large preview

```python
fig = plot_images(
    batch,
    markers=["GFAP"],
    fast_loading=True,
    preview_max_dim=1024,
    image_workers="auto",
    save=False,
    show=False,
)
```

## Notes

- The function raises `ValueError` when no imported images exist or filters
  remove every image row.
- `getImageTable(include_summary=True)` refreshes condition and factor metadata
  from the summary table before plotting.
- `subject_filter` is the preferred name, but the code still accepts
  `animal_filter`.
- ROI outlines depend on ROI coordinate metadata. Missing ROI geometry does not
  make the image table itself invalid.
- Use `plot_representative_images` when you need a curated figure and copied
  source-image assets.

## See Also

- [Image panels](../plot-types/image-panels.md)
- [Image table](../data-structures/image-table.md)
- [ROI tables](../data-structures/roi-tables.md)
- [plot_representative_images](plot_representative_images.md)
- [Saving](../parameters/saving.md)
