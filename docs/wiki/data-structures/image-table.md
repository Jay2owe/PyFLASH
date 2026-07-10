# Image Table

## Summary

The image table is a metadata table that tells PyFLASH where image files are,
which subject and marker they belong to, and how to arrange ROI panels. It is
stored on processed objects as `.images`. A nested lookup dictionary,
`.imagesDict`, is rebuilt from the same table for quick subject/marker/ROI path
lookup.

The table stores paths and labels, not the image pixels needed for long-term
serialization.

## Where It Appears

- `Experiment.images` after `Experiment.importImages()` or `Experiment.processData(import_images=True)`.
- `Batch.images` after `Batch.importImages()` or `Batch.processData(import_images=True)`.
- `Experiment.getImageTable(include_summary=True)` and `Batch.getImageTable(include_summary=True)`.
- UI image helpers and image plot functions.

## Required Fields

The base image table fields are:

| Field | Meaning |
|---|---|
| `AnimalName` | Subject/sample folder name. |
| `Marker` | Marker parsed from the image filename. |
| `ROI` | ROI part parsed from the image filename. This can be blank when the filename has no ROI suffix. |
| `ImageName` | Image file stem without extension. |
| `ImagePath` | Local path to the image file. |
| `Extension` | Lowercase file extension such as `.png`, `.tif`, or `.jpg`. |

Batch image tables also include:

| Field | Meaning |
|---|---|
| `Experiment` | Source experiment name before batch concatenation. |

## Optional Fields

When `include_summary=True`, PyFLASH attaches summary metadata by `AnimalName`:

| Field | Meaning |
|---|---|
| `Condition` | Group label from the summary table. |
| Factor columns | Columns such as `Diagnosis`, `Sex`, or `Time` from the group list. |

Other image-related tables can include `representative_images`, a user-managed
selection table for representative panels. That table is separate from `.images`
but usually shares fields such as `AnimalName`, `Marker`, and `ImageName`.

## Example

```text
| Experiment | AnimalName | Condition | Marker | ROI | ImageName | ImagePath | Extension |
|---|---|---|---|---|---|---|---|
| Exp_01 | Mouse_01 | Control | GFAP | LHSCN | GFAP_LHSCN | /path/to/images/Mouse_01/GFAP_LHSCN.png | .png |
| Exp_01 | Mouse_01 | Control | DAPI | LHSCN | DAPI_LHSCN | /path/to/images/Mouse_01/DAPI_LHSCN.png | .png |
```

Nested lookup form:

```python
image_path = batch.imagesDict["Mouse_01"]["GFAP"]["LHSCN"]
```

## Produced By

- `Experiment.importImages()`, which scans image folders under the experiment root.
- `Batch.importImages()`, which concatenates experiment image tables and adds `Experiment`.
- `getImageTable(include_summary=True)`, which can refresh summary metadata.
- UI helper functions that expose the object image table without importing Streamlit.

## Consumed By

- [`plot_images`](../functions/plot_images.md).
- [`plot_representative_images`](../functions/plot_representative_images.md).
- Representative image selection helpers in the UI service layer.
- Image-related workflow and troubleshooting pages.

## Notes

- `import_images=False` leaves `.images` as `None` on processed objects and `.imagesDict` empty.
- `getImageTable(include_summary=False)` returns only the base image metadata columns that exist on the table.
- Image files are found by scanning known image folders. For current ImageJ-style exports, PyFLASH looks under `Results/Presentation Images/Images` and related analysis-image folders.
- Image table sorting uses experiment, group, subject, ROI drawing order, marker, and image name when those fields are available.
- Pickle serialization removes any `ImageArray` column if it exists, so rely on `ImagePath` for durable references.

## See Also

- [Image panels](../plot-types/image-panels.md)
- [Plot images](../functions/plot_images.md)
- [Representative images](../functions/plot_representative_images.md)
- [Figure folders](../outputs/figure-folders.md)
