# UI Services

## Summary

`PyFLASH/ui/services.py` is the pure-Python adapter layer that sits between the
Streamlit screens and the PyFLASH analysis code. Streamlit pages call functions
here (`open_pickle`, `run_create_batch`, `summary_table`, `available_plots`,
`run_plot_spec`, `run_image_grid`, ...); each one wraps an *existing* PyFLASH
function rather than reimplementing analysis logic. Keeping this seam pure Python
makes the UI unit-testable in an environment with no Streamlit installed.

## The Hard Invariant

`PyFLASH.ui.services` must **never** import `streamlit` at top level — not the
module, not a `from streamlit import ...`. All Streamlit usage lives in
`PyFLASH/ui/app.py` and `PyFLASH/ui/pages/`. Equally, a bare `import PyFLASH`
must not pull in Streamlit or the heavy plotting/stats stack: `PyFLASH/__init__.py`
exposes `plotting`, `pipeline`, `modelling`, and `stats` as lazy PEP 562
attributes, so a UI landing page can confirm a clean core import (via
`services.package_info()`) without paying for matplotlib/scipy/statsmodels.

Practical consequences when editing `services.py`:

- Import from concrete core modules (`PyFLASH.factory`, `PyFLASH.serialization`,
  `PyFLASH.export`, `PyFLASH.ui.project_io`, `PyFLASH.utils`), not from
  `streamlit`.
- Do heavy plotting work by dispatching into `PyFLASH.plotting` inside the
  function body (lazy), never at module top.
- Keep functions side-effect-light and return plain Python / pandas objects that
  a page can render; leave `st.*` calls to the page.

## How Pages Call Services

Each screen under `PyFLASH/ui/pages/` (conditions, plots, images, ...) imports
`PyFLASH.ui.services` and calls one adapter per user action, then renders the
returned object with Streamlit widgets. Conditions are rebuilt through
`PyFLASH.ui.project_io.build_condition_list` (see [Project Files](project-files.md)),
not by pickling group/condition objects.

## Tests That Guard The Boundary

`tests/test_ui_services.py` is the enforcement:

- `test_importing_services_does_not_import_streamlit` — asserts `streamlit` is
  not in `sys.modules` after importing the adapter.
- `test_services_module_has_no_streamlit_attribute` — asserts the module has no
  top-level `streamlit` symbol.
- `test_package_info_reports_clean_import` — the core import smoke test.

Plus round-trip and table tests for the individual adapters. Page-level behaviour
is covered by `tests/test_ui_plots.py`, `tests/test_ui_images.py`, and
`tests/test_ui_conditions.py`.

## See Also

- [Project Files](project-files.md)
- [Testing Map](testing-map.md)
- [Launch the UI](../getting-started/launch-the-ui.md)
- [Use the Streamlit UI](../workflows/use-the-streamlit-ui.md)
