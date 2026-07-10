# Troubleshooting Folder Context

This folder is for problem-solving pages. It should help users recognize common
failure modes and fix them without reading source code.

## What Belongs Here

Add pages for recurring problems such as:

- `import-errors.md`: missing package, optional dependency, or wrong Python
  environment.
- `moved-pickles.md`: saved objects whose paths no longer match the current
  machine, and when to use `normalize_paths`.
- `missing-columns.md`: column selection, renamed columns, display labels, and
  summary-table expectations.
- `conditions-do-not-match.md`: condition labels, factors, crossed designs, and
  animal-name matching.
- `no-plots-saved.md`: `save`, `fig_path`, output folders, dry runs, and
  permission/path issues.
- `image-loading.md`: missing image files, slow image import, optional image
  backends, and representative panels.
- `invalid-plot-spec.md`: spec validation errors, unknown registry names, and
  bad parameter names.
- `ui-problems.md`: Streamlit launch, project files, folder picking, and
  service-layer errors.
- `slow-model-sweeps.md`: feature counts, model presets, cross-validation,
  checkpointing, resume, and parallel settings.
- `statistics-look-wrong.md`: group sizes, normality, corrections, comparisons,
  missing data, and excluded values.

## Page Shape

Use this shape:

```markdown
# Problem title

## Symptoms
Messages, outputs, or behavior the user will see.

## Likely Causes
Short list of common causes.

## Fix
Concrete steps or commands.

## Check
How to confirm the issue is resolved.

## Related Pages
Links to relevant function, parameter, workflow, or output docs.
```

## Writing Rules

- Lead with the practical fix.
- Include exact error fragments only when they are stable and useful for search.
- Do not blame the user. Explain what PyFLASH expected and what to check.
- Keep private local paths out of examples.
- Link to source-level developer docs only when the fix is maintainer-facing.

## Source Checks

Use these files when writing troubleshooting pages:

- `PyFLASH/serialization.py`
- `PyFLASH/utils.py`
- `PyFLASH/experiment.py`
- `PyFLASH/dataframe.py`
- `PyFLASH/conditions.py`
- `PyFLASH/spec.py`
- `PyFLASH/plotting.py`
- `PyFLASH/modelling.py`
- `PyFLASH/ui/services.py`
- tests that assert error handling
