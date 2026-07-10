# ROI Tables

## Summary

ROI tables describe region names, image-panel ROI labels, and optional ROI
coordinates or bounds. PyFLASH uses them to assign `Region` and `ImageROI`
labels, normalize summaries by ROI volume, draw locations, and align image
panels with the ROI drawing order.

There are several related ROI tables rather than one universal schema:

- ROI property CSV tables from ImageJ, such as `SCN ROI Properties.csv`.
- ROI zip coordinate records stored as `Experiment.data["ROIs"].df` and
  `Experiment.data["ROIs To Draw"].df`.
- `Experiment.master_region`, a compact animal-region-image label map.

## Where It Appears

- `Experiment.data["<base> ROI Properties"].df`.
- `Experiment.data["ROIs"].df` for cropped ROI records.
- `Experiment.data["ROIs To Draw"].df` for source/full ROI records.
- `Experiment.master_region` and backward-compatible `Experiment.master_scn`.
- Marker tables after `assign_region()` adds or aligns `ImageROI`.
- `getRegionDict()` output used by iteration and ROI-aware plotting.

## Required Fields

For most ROI-aware analysis, these normalized fields are enough:

| Field | Meaning |
|---|---|
| `AnimalName` | Subject identifier. |
| `Region` | Concrete region instance, such as `SCN1`. |
| `ROI` | ROI label associated with the row. In row-level ROI property and marker tables this may be a concrete value such as `SCN1`; PyFLASH derives the base/family such as `SCN` when building ROI summaries or resolving ROI-base parameters. |

For image panel alignment:

| Field | Meaning |
|---|---|
| `ImageROI` | Image-panel label, commonly hemisphere plus ROI base, such as `LHSCN` or `RHSCN2`. |

For ROI zip coordinate records, useful identifier fields include:

| Field | Meaning |
|---|---|
| `ROIKey` | ROI zip entry key for the current record. |
| `SourceROIKey` | Source/full ROI key used to derive image bounds. |
| `Region` | Normalized ROI label built from the ROI key. Raw zip imports may briefly use `SCN`, but PyFLASH normalizes that column to `Region` when wrapping the table. |
| `ROINameRaw` | Original ROI name before final labeling. |

## Optional Fields

Coordinate and bounds fields are present when they can be read from ROI files:

| Field | Meaning |
|---|---|
| `x`, `y` | Polygon coordinate arrays or lists. |
| `left`, `top`, `right`, `bottom`, `width`, `height` | Bounds for the current ROI. |
| `ImageMinX`, `ImageMinY`, `ImageMaxX`, `ImageMaxY` | Source-image bounds inferred from the uncropped ROI. |
| `ImageLeft`, `ImageTop`, `ImageRight`, `ImageBottom`, `ImageWidth`, `ImageHeight` | Source-image frame dimensions. |

ROI property tables can also carry measurement fields such as area, volume,
width, and height. PyFLASH normalizes some of these into summary columns such
as `ROI_Area`, `ROI_Volume`, and `ROI_Thickness`.

## Example

Compact `master_region` style:

```text
| AnimalName | Region | ImageROI |
|---|---|---|
| Mouse_01 | SCN1 | LHSCN |
| Mouse_01 | SCN2 | RHSCN |
| Mouse_02 | SCN1 | LHSCN |
```

ROI coordinate record style:

```text
| AnimalName | Region | ImageROI | ROIKey | SourceROIKey | left | top | width | height |
|---|---|---|---|---|---:|---:|---:|---:|
| Mouse_01 | SCN1 | LHSCN | Mouse_01_SCN_Cropped | Mouse_01_SCN | 12 | 30 | 80 | 65 |
```

## Produced By

- `Experiment.importCSVs()`, which reads ROI property CSV files and ROI zip files.
- ROI zip readers inside `experiment.py`, when coordinate metadata can be extracted.
- `Experiment.assign_region()`, which builds `master_region` and applies `ImageROI` labels to marker tables.
- `Experiment.createSummary()`, which uses ROI property rows to count sections and derive ROI normalization columns.

## Consumed By

- `Experiment.addVentricleDistances()`.
- `Experiment.assign_region()` and `getRegionDict()`.
- [`plot_locations`](../functions/plot_locations.md) and ROI-aware image/marker plots.
- Summary-building code that normalizes counts by ROI volume.
- ROI parameters documented in [ROI](../parameters/roi.md).

## Notes

- Older exports with an `SCN` column are converted to normalized `Region` values such as `SCN1`.
- If no explicit ROI base is present, PyFLASH falls back to `SCN`.
- Hemisphere values are normalized where present. Without hemisphere metadata, PyFLASH can fall back to alternating left/right labels per animal.
- `ImageROI` labels are for image arrangement and may differ from raw `Region` values.
- Coordinate fields are best-effort. Some ROI files or dependencies may not expose full polygon bounds.

## See Also

- [ROI parameters](../parameters/roi.md)
- [Marker Tables](marker-tables.md)
- [Image Table](image-table.md)
- [Location plots](../plot-types/location-plots.md)
