# Data Structures Folder Context

This folder explains the tables, files, and schemas that PyFLASH functions read
and write. It is separate from `../object-types/`: object pages explain Python
objects, while data-structure pages explain the data inside them.

## What Belongs Here

Add pages for recurring data shapes such as:

- `summary-table.md`: `batch.summary`, required identifier columns, condition
  columns, marker metric columns, and factor columns.
- `marker-tables.md`: raw marker, object, antibody, and colocalisation tables.
- `image-table.md`: image metadata, marker panels, ROI image names, and image
  path handling.
- `roi-tables.md`: region/ROI names, ROI bases, hemispheres, and coordinate
  data.
- `condition-specs.md`: JSON-style condition specs used by the UI services.
- `plot-spec-files.md`: YAML/TOML/JSON plot spec structure for `run_spec`.
- `exclusion-ledgers.md`: recorded manual and outlier exclusion data.
- `pipeline-manifests.md`: manifest files written by pipeline runs.

## Page Shape

Use this shape:

```markdown
# Data structure name

## Summary
What the structure represents.

## Where It Appears
Objects, functions, folders, or files that use it.

## Required Fields
Columns or keys required for normal use.

## Optional Fields
Common optional columns or keys.

## Example
Small table, JSON, YAML, or Python example.

## Produced By
Functions that create it.

## Consumed By
Functions that read it.

## Notes
Naming conventions, missing values, sentinel values, or compatibility details.
```

## Source Checks

Use these files before writing:

- `PyFLASH/experiment.py`
- `PyFLASH/batch.py`
- `PyFLASH/dataframe.py`
- `PyFLASH/export.py`
- `PyFLASH/spec.py`
- `PyFLASH/exclusions.py`
- `PyFLASH/pipeline_io.py`
- `PyFLASH/ui/project_io.py`

Include small examples, not private experiment data.
