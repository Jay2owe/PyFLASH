# Representative Panels

## Goal

Render a curated representative-image panel from stored representative
selection metadata.

## Code

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import numpy as np
import pandas as pd
from PIL import Image
from PyFLASH.plotting import plot_representative_images

with TemporaryDirectory() as tmp:
    root = Path(tmp)
    image_records = []
    selection_records = []

    for animal, condition, offset in [
        ("C1", "Control", 60),
        ("A1", "AD", 150),
    ]:
        image = np.zeros((48, 48, 3), dtype=np.uint8)
        image[:, :, 2] = offset
        image[14:34, 14:34, 2] = min(offset + 80, 255)
        path = root / f"{animal}_DAPI.png"
        Image.fromarray(image).save(path)

        image_records.append({
            "Experiment": "Synthetic",
            "Condition": condition,
            "AnimalName": animal,
            "ROI": "SCN",
            "Marker": "DAPI",
            "ImageName": path.stem,
            "ImagePath": str(path),
            "Extension": ".png",
        })
        selection_records.append({
            "SelectionGroup": condition,
            "Condition": condition,
            "Experiment": "Synthetic",
            "AnimalName": animal,
            "ROI": "SCN",
            "RepresentativeMarkers": "DAPI",
            "RepresentativeMarkerKey": "dapi",
            "SelectedAt": "2026-07-10T00:00:00",
        })

    batch = SimpleNamespace(
        name="Synthetic",
        images=pd.DataFrame(image_records),
        representative_images=pd.DataFrame(selection_records),
        representative_image_markers=["DAPI"],
        representative_path=str(root / "Representative Images"),
    )

    fig = plot_representative_images(
        batch,
        markers=["DAPI"],
        block_by="all",
        save=False,
        show=False,
        image_backend="pil",
        fast_loading=True,
        preview_max_dim=64,
        progress=False,
    )

    print(fig.PyFLASH_image_df[["Condition", "AnimalName", "ROI"]])
```

## Result

The function returns a representative image figure with matched image rows in
`fig.PyFLASH_image_df`. With `save=True`, PyFLASH would also write the SVG,
`representative_image.csv`, and copied source-image files under
`representative_path`.

## Notes

The `representative_images` table records which animal, condition, ROI, and
marker set was selected. It must match rows in the source image table; otherwise
the function raises a `ValueError`.

## See Also

- [plot_representative_images](../functions/plot_representative_images.md)
- [plot_images](../functions/plot_images.md)
- [Image panels](../plot-types/image-panels.md)
- [Image table](../data-structures/image-table.md)
