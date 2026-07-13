# plot_representative_images

## Summary

`plot_representative_images` draws a panel from stored representative image
selections. It is the function to use after representative images have been
selected in the UI or stored on the source object as `representative_images`.

Registry name: `representative_images`.

## Signature

```python
plot_representative_images(
    source,
    markers=None,
    animal_filter=None,
    subject_filter=None,
    fast_loading=False,
    preview_max_dim=None,
    image_backend="auto",
    image_workers=None,
    image_adjustments=None,
    edit_mode=False,
    use_existing_edits=False,
    draw_rois=None,
    progress=True,
    _preview_single_image=False,
    **kwargs,
)
```

Common keyword arguments in `**kwargs` include `save`, `show`, `verbose`,
`merge`, `merge_label`, `scale_bar`, `scale_bar_location`, `scale_bar_size`,
`scale_bar_units`, `image_width_microns`, `pixel_size`, `tile_size`, `tile_gap`,
`tile_gap_units`, `title`, `block_layout`, `block_by`, and `stack_by`.

## Input Object Types

| Object type | Accepted? | Notes |
|---|---:|---|
| `Batch` | Yes | Main supported input. Uses `representative_images`, image table, and `representative_path`. |
| `Experiment` | Yes | Works when representative selections and image paths are available. |
| `MiniExperiment` | Usually no | Flat CSV objects do not normally carry imported image selections. |
| `pandas.DataFrame` | No | The function needs an object with representative selections and image paths. |

## Parameters

| Parameter | Type | Default | Meaning |
|---|---|---:|---|
| `source` | `Batch` or `Experiment` | required | Object containing image metadata and representative selections. |
| `markers` | `str`, list-like, or `None` | `None` | Representative marker set to plot. |
| `subject_filter` | `str`, list-like, or `None` | `None` | Subject filter. Alias: `animal_filter`. |
| `fast_loading` | `bool` | `False` | Use lower-resolution loading when possible. |
| `preview_max_dim` | `int` or `None` | `None` | Downsample previews to this longest-side pixel size. |
| `image_backend` | `str` | `"auto"` | Image reader. |
| `image_workers` | `int`, `"auto"`, or `None` | `None` | Parallel image-loading workers. |
| `image_adjustments` | `dict` or `None` | `None` | Per-marker brightness/contrast settings. |
| `edit_mode` | `bool` | `False` | Open the image-adjustment editor for selected representative images. |
| `use_existing_edits` | `bool` | `False` | Reuse saved image edits. |
| `draw_rois` | `bool`, marker-panel spec, or `None` | `None` | Draw ROI outlines on matching image panels. |
| `progress` | `bool` | `True` | Show progress for table, filter, block, load, render, and save steps. |
| `save` | `bool` | `True` | Save the representative figure and export assets. Passed through `**kwargs`. |
| `show` | `bool` | `True` | Keep the figure open. Passed through `**kwargs`. |
| `merge` | `bool` | `False` | Include merged marker panels. Passed through `**kwargs`. |
| `block_by` | `str` | `"Condition"` | Group representative blocks by condition or another column. |
| `stack_by` | `str` or `None` | `None` | Alias route to `block_by`. |
| `block_layout` | `str` | `"horizontal"` | Layout mode for representative blocks. |

## Parameter Options

### `image_backend` options

| Option | Behavior |
|---|---|
| `"auto"` (default) | Let PyFLASH choose an available image reader. |
| `"tifffile"` | Read images with tifffile. |
| `"cv2"` | Read images with OpenCV. |
| `"imageio"` | Read images with imageio. |
| `"pil"` | Read images with Pillow. |

## Returns

| Return value | Type | Meaning |
|---|---|---|
| `fig` | `matplotlib.figure.Figure` | Representative image panel. |

The returned figure has these PyFLASH attributes:

| Attribute | Meaning |
|---|---|
| `fig.PyFLASH_image_df` | Filtered image rows matched to representative selections. |
| `fig.PyFLASH_representative_blocks` | Block layout records used to render the figure. |
| `fig.PyFLASH_save_path` | Saved figure path, or `None` when `save=False`. |
| `fig.PyFLASH_image_adjustments` | Effective image adjustments. |

## Saved Outputs

With `save=True`, the function writes:

- a representative figure named `representative_images.svg`, or
  `representative_images_by_<block>.svg` when grouped by another block;
- the same figure stem with `_merged` appended when `merge=True`;
- `representative_image.csv`, with selection metadata and copied-image names;
- copied image files for the selected marker/condition/animal/ROI rows.

The export folder is under `source.representative_path`, then source or
experiment name, then the marker set. If `subject_filter` is set, a filtered
subfolder is added. Alias: `animal_filter`.

## Examples

### Render stored selections without saving

```python
from PyFLASH.plotting import plot_representative_images

fig = plot_representative_images(
    batch,
    markers=["DAPI"],
    save=False,
    show=False,
)

print(fig.PyFLASH_image_df[["Condition", "AnimalName", "ROI"]])
```

### Save a merged representative panel

```python
plot_representative_images(
    batch,
    markers=["DAPI", "GFAP"],
    merge=True,
    block_by="Condition",
    scale_bar=True,
    save=True,
    show=False,
)
```

### Reuse saved edits for a final panel

```python
fig = plot_representative_images(
    batch,
    markers=["DAPI", "GFAP"],
    use_existing_edits=True,
    image_backend="pil",
    save=True,
    show=False,
)
print(fig.PyFLASH_save_path)
```

## Notes

- The function raises `ValueError` if no representative images have been
  selected or if stored selections no longer match imported image rows.
- Representative selection matching uses shared fields such as `Experiment`,
  `Condition`, `AnimalName`, and `ROI`.
- Exported CSV files drop the internal `RepresentativeMarkerKey` column.
- Use `plot_images` for browsing all imported images before choosing
  representative selections.

## See Also

- [Image panels](../plot-types/image-panels.md)
- [Image table](../data-structures/image-table.md)
- [plot_images](plot_images.md)
- [Figure folders](../outputs/figure-folders.md)
