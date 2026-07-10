# Image Panels

## Use This When

Use image panels when you need to inspect the microscopy images behind the
tables. `plot_images` browses imported source images. `plot_representative_images`
draws a curated panel from images that have already been selected as
representative examples.

These plots are visual checks and figure panels, not statistical tests.

## Input Data

Image panels need an image table on the input object. A `Batch` or `Experiment`
must have run image import, either through `processData(import_images=True)`,
`importImages()`, or `getImageTable()`.

The image table must include image paths and labels such as `AnimalName`,
`Marker`, `ROI`, `ImageName`, and `ImagePath`. Representative panels also need a
`representative_images` table that records the selected subjects, groups,
ROIs, and marker set.

Raw `pandas.DataFrame` summary tables are not enough for these plots because
they do not carry image paths.

## Main Functions

| Function | Registry name | Use |
|---|---|---|
| [`plot_images`](../functions/plot_images.md) | `images` | Browse or save grids of imported images, optionally filtered by marker, subject, or ROI. |
| [`plot_representative_images`](../functions/plot_representative_images.md) | `representative_images` | Draw saved representative selections and export the selected source-image files. |

## Common Options

| Option | Meaning |
|---|---|
| `markers` | Marker names to display. Use a list for several markers. |
| `subject_filter` / `animal_filter` | Restrict the image rows to one or more subjects. |
| `roi_filter` | Restrict `plot_images` to matching ROI labels. |
| `merge` | Add merged marker panels when several markers are requested. |
| `draw_rois` | Draw ROI outlines when ROI geometry is available. |
| `scale_bar` | Add a scale bar using image width or pixel-size information. |
| `fast_loading`, `preview_max_dim`, `image_workers` | Speed controls for large images. |
| `edit_mode`, `image_adjustments`, `use_existing_edits` | Interactive or saved brightness/contrast adjustments. |

## Outputs

Both functions return a `matplotlib.figure.Figure`. The returned figure carries
PyFLASH metadata attributes such as the filtered image table and saved path.

With `save=True`, `plot_images` writes a figure under the object's image figure
folder. `plot_representative_images` writes a representative image figure, a
`representative_image.csv` file, and copied source-image files in the
representative export folder.

## Examples

Browse one marker without saving:

```python
from PyFLASH.plotting import plot_images

fig = plot_images(batch, markers=["DAPI"], save=False, show=False)
print(fig.PyFLASH_image_df[["AnimalName", "Marker", "ROI"]].head())
```

Render representative panels after selections have been stored:

```python
from PyFLASH.plotting import plot_representative_images

fig = plot_representative_images(
    batch,
    markers=["DAPI", "GFAP"],
    merge=True,
    save=True,
    show=False,
)
print(fig.PyFLASH_save_path)
```

## Interpretation

Use image panels to check whether the plotted measurements correspond to
credible images, whether ROI labels match the expected anatomy, and whether
representative examples are balanced across conditions. Do not treat a
representative image panel as evidence of a group effect unless it is paired
with a quantitative summary and an appropriate statistical analysis.

For very large image sets, start with `fast_loading=True` or
`preview_max_dim=1024`, then rerun the final panel without preview downsampling
if full-resolution output matters.

## See Also

- [Image table](../data-structures/image-table.md)
- [ROI tables](../data-structures/roi-tables.md)
- [ROI selection](../parameters/roi.md)
- [Figure folders](../outputs/figure-folders.md)
- [Location and 3D plots](location-plots.md)
