# Experiment

## Summary

`Experiment` represents one full FLASH/ImageJ experiment export. It resolves the
experiment folder layout, imports marker and attribute CSV files, processes
spatial and colocalisation measurements, builds subject-level summary tables,
and records image metadata.

Most users do not instantiate `Experiment` directly. [`create_batch`](../functions/create_batch.md)
creates `Experiment` objects while building a [`Batch`](batch.md).

## How To Create It

Usually through `create_batch`:

```python
from PyFLASH import GroupBuilder, create_batch

groups = (
    GroupBuilder("Genotype")
    .add("WT", short="WT", color="grey")
    .add("KO", short="KO", color="blue")
    .build()
)

batch = create_batch(
    "mouse-study",
    groups,
    "/path/to/batch-output",
    experiments={"experiment-1": "/path/to/experiment-folder"},
    import_images=False,
)

experiment = batch.experiment_list[0]
```

Manual construction is useful for inspection or advanced workflows:

```python
from PyFLASH import Experiment

experiment = Experiment("exp-1", "/path/to/experiment-folder")
experiment.processData(import_images=False)
```

Supported folder inputs include legacy exports with `Data Analysis/` and newer
ImageJ-style exports with `Results/Tables/`.

## Important Attributes

| Attribute | Meaning |
|---|---|
| `name` | Human-readable experiment name. |
| `filePath` | Resolved folder containing importable data tables. |
| `source_root` | Root experiment folder inferred from `filePath`. Output folders are created relative to this root. |
| `data_layout` | Resolved input layout name, such as `"legacy"`, `"imagej-results"`, or `"unknown"`. |
| `data` | Dictionary of imported marker, object, ROI, behavior, or attribute tables. Values are marker objects with `.df`. |
| `markers` | Set of marker names discovered during import. |
| `threshold` | Colocalisation threshold. Defaults to `Config.THRESHOLD` unless passed to the constructor. |
| `condition_list` | Group metadata assigned by `set_condition_list`, usually through `Batch.processData`. |
| `conditions` | Flattened group objects from the group list. |
| `factor` | List of factor names from the group list. |
| `factorDict` | Mapping from factor name to its group objects. |
| `summaries` | Dictionary of subject-level summary tables keyed by region of interest base. |
| `summary` | Primary summary table. It returns the `SCN` summary when present, otherwise the first available summary. |
| `master_region` | Region mapping table produced by `assign_region`. |
| `images` | Image metadata table, or an empty table if no images were found. |
| `imagesDict` | Lookup dictionary derived from `images`. |
| `image_root` | Folder where images were discovered, when available. |
| `fig_path`, `image_fig_path`, `representative_path`, `legend_path`, `data_path` | Standard output folders under the experiment root. |
| `csv_path`, `column_path`, `attribute_path` | CSV export folders under the experiment root. |

## Common Methods

| Method | Use |
|---|---|
| `importCSVs(progress=True)` | Import all supported CSV and ROI ZIP files from the experiment folder. |
| `processData(import_images=True, progress=True)` | Run the full import, measurement, summary, path, and optional image pipeline. |
| `createSummary(progress=True)` | Build `.summaries` and `.summary` from imported marker tables. |
| `set_condition_list(condition_list)` | Attach groups, factors, and factor columns to summaries and data tables. |
| `addClosestDistances(progress=True)` | Add closest-marker distance columns for object and cell markers. |
| `addVentricleDistances(progress=True)` | Add ventricle distance columns when ROI data is present. |
| `assign_region()` | Build the region mapping used for iteration and image matching. |
| `assign_scn_number()` | Backward-compatible alias for `assign_region()`. |
| `createSavePaths()` | Populate standard output path attributes. |
| `importImages(progress=True)` | Discover image files and build the image metadata table. |
| `getImageTable(include_summary=True)` | Return image metadata, optionally merged with summary metadata. |
| `getDisplaySummary(roi_base=None)` | Return a display-only summary copy with readable labels. |
| `save_csvs()` | Save summary and marker CSV outputs. |
| `save_column_csvs()` | Save one CSV per summary column. |
| `save_attribute_csvs()` | Save imported marker and attribute tables. |
| `getRegionDict(roi_base=None)` | Return condition to animal to region mappings. |
| `getSCNDict()` | Backward-compatible shortcut for `getRegionDict(roi_base="SCN")`. |
| `info()` | Print a short console summary of the experiment. |

## Accepted By

Many plotting functions and helpers accept an `Experiment` because it has the
same core fields as a `Batch`: `summary`, `summaries`, `data`,
`condition_list`, `factor`, `factorDict`, and output paths. Multi-experiment
workflows should usually pass a `Batch` instead.

## Returned By

`Experiment` objects are created inside [`create_batch`](../functions/create_batch.md).
[`load_state`](../functions/load_state.md) can return an `Experiment` if that is
what was saved.

## Examples

Inspect imported tables after creating a batch:

```python
experiment = batch.experiment_list[0]

print(experiment.name)
print(experiment.data_layout)
print(sorted(experiment.data))
print(experiment.summary.head())
```

Inspect one marker table:

```python
marker = experiment.data["GFAP"]
print(marker.name)
print(marker.df.head())
```

Resolve whether a folder looks importable:

```python
from PyFLASH.experiment import is_experiment_folder, resolve_experiment_paths

print(is_experiment_folder("/path/to/experiment-folder"))
print(resolve_experiment_paths("/path/to/experiment-folder"))
```

## Notes

- `Experiment` is for full FLASH/ImageJ folder exports. Use
  [`MiniExperiment`](mini-experiment.md) for flat CSV folders and
  [`DataFrameExperiment`](dataframe-experiment.md) for in-memory tables.
- `summary` is a property backed by `summaries`; assigning a DataFrame to
  `summary` stores it under the `"SCN"` key for backward compatibility.
- Imported marker tables are normalized during import. Column names and
  colocalisation aliases may differ from raw CSV headers.
- Image import records paths and metadata. It does not need to load every image
  array into memory for ordinary summary analysis.

## See Also

- [Batch](batch.md)
- [MiniExperiment](mini-experiment.md)
- [Marker objects](markers.md)
- [Summary table](../data-structures/summary-table.md)
- [Marker tables](../data-structures/marker-tables.md)
- [Image table](../data-structures/image-table.md)
