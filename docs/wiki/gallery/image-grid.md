# Image Grid

## Goal

Create a minimal image table and browse marker images with `plot_images`.

## Code

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import numpy as np
import pandas as pd
from PIL import Image
from PyFLASH.plotting import plot_images

with TemporaryDirectory() as tmp:
    root = Path(tmp)
    records = []
    for animal, condition, offset in [
        ("C1", "Control", 40),
        ("A1", "AD", 120),
    ]:
        for marker, channel in [("DAPI", 2), ("GFAP", 1)]:
            image = np.zeros((48, 48, 3), dtype=np.uint8)
            image[:, :, channel] = offset
            image[12:36, 12:36, channel] = min(offset + 90, 255)
            path = root / f"{animal}_{marker}.png"
            Image.fromarray(image).save(path)
            records.append({
                "Experiment": "Synthetic",
                "Condition": condition,
                "AnimalName": animal,
                "ROI": "SCN",
                "Marker": marker,
                "ImageName": path.stem,
                "ImagePath": str(path),
                "Extension": ".png",
            })

    batch = SimpleNamespace(name="Synthetic", images=pd.DataFrame(records))

    fig = plot_images(
        batch,
        markers=["DAPI", "GFAP"],
        ncols=2,
        save=False,
        show=False,
        image_backend="pil",
        fast_loading=True,
        preview_max_dim=64,
        progress=False,
    )

    print(fig.PyFLASH_image_df[["AnimalName", "Marker", "ROI"]])
```

## Result

The function returns a Matplotlib figure. The figure's `PyFLASH_image_df`
attribute stores the filtered image rows that were rendered. No files are saved
because `save=False`.

## Notes

Real image grids need a `Batch` or experiment object with imported image
metadata. A summary-only table is not enough because `plot_images` needs
`ImagePath` values that point to source image files.

## See Also

- [plot_images](../functions/plot_images.md)
- [Image panels](../plot-types/image-panels.md)
- [Image table](../data-structures/image-table.md)
- [Figure folders](../outputs/figure-folders.md)
