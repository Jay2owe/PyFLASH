# Developer Folder Context

This folder is for maintainer-facing documentation. It should help future
agents and developers extend PyFLASH without breaking user workflows.

## What Belongs Here

Use this folder for implementation-facing topics such as:

- how the plot registry maps short names to callables;
- how the describe/report layer is maintained;
- how the Streamlit-free UI service layer calls core PyFLASH code;
- how project JSON files are built and loaded;
- how to add a plot or pipeline function safely;
- which tests protect a subsystem;
- how generated reference docs are refreshed.

Do not use this folder for normal user API pages. Put those in `../functions/`,
`../concepts/`, or `../workflows/`.

## Project Constraints To Preserve

- `PyFLASH.ui.services` must stay free of top-level `streamlit` imports.
- Core `import PyFLASH` should not import Streamlit or heavy plotting
  dependencies.
- New registered plots should update `PyFLASH/spec.py::PLOT_REGISTRY` and the
  describe coverage sets.
- Matplotlib SVG output should keep text as editable `<text>` elements.
- Generated graph artifacts and local analysis outputs should not be committed.

Check the root `AGENTS.md` and `CLAUDE.md` before writing maintainer docs,
because they contain active project rules.

## Planned Pages

Useful future developer pages:

- `plot-registry.md`: `PLOT_REGISTRY`, registry aliases, pipeline callables, and
  describe status.
- `adding-a-plot.md`: source changes, registration, docs, tests, and reference
  refresh.
- `ui-services.md`: pure-Python adapter layer, Streamlit page calls, and test
  boundaries.
- `project-files.md`: Streamlit project JSON schema and condition rebuild.
- `structured-results.md`: `PyFLASH.report`, describe coverage, and result
  manifests.
- `testing-map.md`: which tests cover loading, plotting, UI services, specs,
  and pipeline outputs.
- `docs-maintenance.md`: how to keep wiki pages, generated references, and API
  indexes in sync.

## Source Checks

Use these files when writing developer pages:

- `PyFLASH/spec.py`
- `PyFLASH/plotting.py`
- `PyFLASH/pipeline.py`
- `PyFLASH/report.py`
- `PyFLASH/ui/services.py`
- `PyFLASH/ui/project_io.py`
- `PyFLASH/__init__.py`
- `scripts/update_pyflash_references.py`
- relevant tests in `tests/`

Keep developer docs specific and operational. A future agent should be able to
use them as a checklist before editing code or adding documentation.
