# UI Problems

## Symptoms

- `pyflash-ui` is not found, or the app fails before the first page opens.
- The folder picker lists no valid experiments, or every candidate shows a
  cross.
- Building a batch from the UI raises `No experiment folders found in ...`.
- The conditions page shows a validation error containing `Did you mean '...'?`.
- Export or plot pages surface a regex or spec-validation error.

## Likely Causes

- Streamlit (and PyYAML) are not installed — they ship only in the `ui` extra.
- The chosen folder is an individual experiment when the page expects the parent
  batch root, or vice versa. Discovery scans the immediate child folders of the
  root you give it.
- An experiment folder lacks the expected layout. A folder is valid when it
  contains a `Data Analysis/` subfolder (with `Objects`/`Attributes`/`ROI
  Intensities` or CSVs) or a `Results/Tables` layout.
- The condition spec has a misspelled short name or an ambiguous crossed
  comparison.
- A malformed include/exclude regex was passed to Excel export.

## Fix

Install the UI extra into the same environment as PyFLASH, then launch:

```bash
pip install -e ".[ui]"
pyflash-ui
```

The equivalent manual launch is:

```bash
python -m streamlit run PyFLASH/ui/app.py
```

Point the folder picker at the parent that contains experiment subfolders, not
at a single experiment. You can check any candidate folder without the browser
through the Streamlit-free service layer:

```python
from PyFLASH.ui import services

print(services.validate_experiment_folder("path/to/experiment"))
print(services.discover_experiments("path/to/batch/root"))
```

For a conditions error, rebuild the spec and inspect it before creating the
batch; the builder's `Did you mean '...?'` message names the closest valid short
name. For an export regex error, fix the offending pattern (validate it with
`services.validate_regex([...])`).

## Check

Run a minimal service-layer smoke test. This layer never imports Streamlit, so
if it fails, fix the core Python environment before debugging the browser:

```python
from PyFLASH.ui import services

print(services.package_info())   # {'import_ok': True, ...}
```

## Related Pages

- [Launch the UI](../getting-started/launch-the-ui.md)
- [Use the Streamlit UI](../workflows/use-the-streamlit-ui.md)
- [UI services](../developer/ui-services.md)
- [create_batch](../functions/create_batch.md)
- [Group labels do not match](conditions-do-not-match.md)
