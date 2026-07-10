# Outputs Folder Context

This folder explains files and folders produced by PyFLASH. It should help users
find, inspect, and reuse saved results.

## What Belongs Here

Add pages for output families such as:

- `figure-folders.md`: `fig_path`, plot subfolders, aliases, specificity path
  parts, ROI suffixes, and saved image names.
- `pipeline-run-folders.md`: run labels, manifests, tables, figures, and
  overwrite/resume behavior.
- `excel-workbooks.md`: standard IF summary, extended IF summary, behavior
  exports, and extra summary exports.
- `normality-outputs.md`: normality check figures and tables.
- `model-sweep-outputs.md`: score tables, top feature recurrence, prediction
  tables, permutation outputs, and plots.
- `report-records.md`: structured results emitted for describe/report support.
- `pickle-files.md`: saved state files, path rebasing, legacy migration, and
  image array stripping.

## Page Shape

Use this shape:

```markdown
# Output family

## Summary
What is saved and why it matters.

## Created By
Functions, methods, or workflows that write these outputs.

## Folder Layout
Expected folder names and file names.

## File Contents
Important columns, keys, or figure types.

## How To Reuse
Python examples for loading or inspecting the output.

## Notes
Overwrite, cache, compatibility, or path behavior.
```

## Source Checks

Use these files:

- `PyFLASH/utils.py`
- `PyFLASH/export.py`
- `PyFLASH/batch.py`
- `PyFLASH/serialization.py`
- `PyFLASH/pipeline.py`
- `PyFLASH/pipeline_io.py`
- `PyFLASH/modelling.py`
- `PyFLASH/report.py`

Do not document private local output folders such as `Results/` or `No Combo/`
as examples unless the user explicitly asks.
