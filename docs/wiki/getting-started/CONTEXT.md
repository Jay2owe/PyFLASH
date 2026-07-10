# Getting Started Folder Context

This folder is for first-contact documentation. It should help a new user get
from an installed package to a working PyFLASH result with the fewest concepts
possible.

## What Belongs Here

Add short onboarding pages such as:

- `installation.md`: local install, editable install, optional UI extras, and
  dependency checks.
- `first-batch.md`: create or load a `Batch` from experiment folders.
- `first-table-batch.md`: use `from_dataframe` when data is already tabular.
- `first-plot.md`: make one simple plot from a loaded batch.
- `first-plot-spec.md`: run a tiny YAML/TOML/JSON plot spec.
- `launch-the-ui.md`: install UI extras and start the Streamlit interface.
- `where-results-go.md`: the quickest explanation of saved figures, workbooks,
  pickles, and pipeline folders.

These pages should be shorter than workflow pages. They are allowed to omit
advanced options and link to the full reference.

## Page Shape

Use this shape:

```markdown
# Page title

## Goal
One sentence stating what the user will accomplish.

## Before You Start
Minimal assumptions, required files, or installed extras.

## Steps
The shortest reliable sequence.

## Check It Worked
Expected object, output file, or screen state.

## Next
Links to deeper reference, workflow, or troubleshooting pages.
```

## Writing Rules

- Keep examples small and copy-pasteable.
- Avoid explaining every parameter. Link to `../functions/` and
  `../parameters/` for reference detail.
- Use placeholder paths such as `r"C:\path\to\experiment-parent"`.
- Prefer a working path through the package over a survey of alternatives.
- Mention optional extras only where they are needed.

## Source Checks

Use these files when writing getting-started pages:

- `README.md`
- `pyproject.toml`
- `PyFLASH/__init__.py`
- `PyFLASH/factory.py`
- `PyFLASH/dataframe.py`
- `PyFLASH/spec.py`
- `PyFLASH/ui/app.py`
- `PyFLASH/ui/services.py`
- relevant tests in `tests/`
