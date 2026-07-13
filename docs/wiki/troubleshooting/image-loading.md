# Image Loading

## Symptoms

- Image plots raise `No imported images were found.`.
- Image plots raise `No images matched the requested
  marker/animal_filter/roi_filter filters.`.
- Representative-image plots raise `No representative images have been selected
  for this source.` even though ordinary image grids work.
- Individual tiles render the text `Could not load image` instead of a picture.
- Image import or plotting is very slow.

## Likely Causes

- The batch was built with `import_images=False`, so no image table was
  populated.
- No image folder was found at import time. PyFLASH looks for an `Images/`
  folder in the experiment root, plus the FLASH layouts
  `Results/Presentation Images/Images` and
  `Results/Analysis Images/Segmentation`. With none present, import records
  `No Images folder found`.
- The `markers`, `animal_filter`, or `roi_filter` values do not match any rows
  in the image table.
- The project moved and `ImagePath` values no longer point at existing files
  (see [Moved pickles](moved-pickles.md)).
- The selected `image_backend` cannot read a file, or full-resolution plotting
  of many large images is simply slow.

## Fix

Confirm images were imported, then preview one small marker with `save=False`:

```python
from PyFLASH.plotting import plot_images

print(None if getattr(batch, "images", None) is None else batch.images.shape)

plot_images(batch, markers=["DAPI"], save=False, fast_loading=True,
            preview_max_dim=1024)
```

During plotting, `fast_loading=True` and a `preview_max_dim` cap downscale
images while loading, and `image_workers` can load tiles in parallel. Import
itself builds the image metadata table; if import is slow, first check folder
layout and file counts rather than these plotting options. Supported extensions
are `.png`, `.jpg`, `.jpeg`, `.tif`, `.tiff`, `.bmp`.

If a tile shows `Could not load image`, pick an explicit backend with
`image_backend`. See the [`plot_images` reference](../functions/plot_images.md)
on the image plotting page. `"tifffile"` is not installed by the base package,
so `pip install tifffile` if you need it; otherwise confirm the file opens
outside PyFLASH.

For representative panels, select representative images first (or fill the
`representative_images` table) before calling `plot_representative_images`.

## Check

Inspect the imported table before plotting:

```python
print(batch.images[["AnimalName", "Marker", "ROI", "ImagePath"]].head())
print(batch.images["Marker"].value_counts())

from pathlib import Path
print(batch.images["ImagePath"].map(lambda p: Path(p).exists()).value_counts())
```

Match your `markers`/`animal_filter`/`roi_filter` to the values that actually
appear in those columns.

## Related Pages

- [Image table](../data-structures/image-table.md)
- [Image panels](../plot-types/image-panels.md)
- [plot_images](../functions/plot_images.md)
- [plot_representative_images](../functions/plot_representative_images.md)
- [Moved pickles](moved-pickles.md)
