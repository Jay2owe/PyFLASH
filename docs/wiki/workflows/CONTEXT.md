# Workflows Folder Context

This folder is for task-based guides. A workflow page should help a user start
from a real situation and finish with a useful result.

## Page Shape

Use this shape unless another structure is clearer:

```markdown
# Workflow title

## Goal
What the user is trying to do.

## Inputs
Objects, folders, files, columns, or settings needed before starting.

## Minimal Path
The shortest working example.

## Full Workflow
The normal step-by-step version with options.

## Outputs
Returned objects and saved files.

## Troubleshooting
Common failures and what to check.

## Next Steps
Related workflows or function pages.
```

Keep workflows practical. They can link to function pages for complete
parameter tables.

## Planned Pages

Useful future workflow pages:

- `create-a-batch.md`: from experiment folders to a processed `Batch`.
- `build-conditions.md`: simple and crossed condition designs.
- `load-and-rebase-a-pickle.md`: `load_state`, `normalize_paths`, and moved
  data folders.
- `plot-from-python.md`: common plotting patterns from a loaded batch.
- `plot-from-spec.md`: run many plots from YAML/TOML/JSON specs.
- `run-correlation-pipeline.md`: correlation discovery and saved outputs.
- `run-adjusted-linear-model.md`: adjusted means, coefficients, and covariates.
- `run-model-sweep.md`: classifier feature-subset discovery.
- `export-excel-workbooks.md`: standard summary and extended exports.
- `use-the-streamlit-ui.md`: UI workflow from project setup to export.

## Source Checks

Use both code and existing docs:

- Batch creation: `PyFLASH/factory.py`, `PyFLASH/experiment.py`
- Conditions: `PyFLASH/conditions.py`, `PyFLASH/ui/project_io.py`
- Plot specs: `PyFLASH/spec.py`
- Pipelines: `PyFLASH/pipeline.py`
- Exports: `PyFLASH/batch.py`, `PyFLASH/export.py`
- UI services: `PyFLASH/ui/services.py`
- Existing function docs in `../functions/`

Workflow examples should be copy-pasteable but not tied to private local paths.
Use placeholders such as `r"C:\path\to\experiment-parent"`.
