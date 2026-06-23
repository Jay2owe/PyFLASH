# PyFLASH - Agent Guide

PyFLASH is a Python package for processing and analyzing immunofluorescence
confocal microscopy data exported from FLASH/ImageJ workflows. The PyPI
distribution is `PyFLASH-analysis`; the import package is `PyFLASH`.

## Before Broad Search: Query The Knowledge Graph

A local graphify knowledge graph of the Python package and tests lives at
`graphify-out/graph.json` (AST-only: no semantic extraction, no LLM tokens).
Query it before broad `rg`/file scans on architecture questions:

```bash
python -m graphify query "<your question>" --graph graphify-out/graph.json
```

Examples worth trying:

- `python -m graphify query "where is batch creation wired" --graph graphify-out/graph.json`
- `python -m graphify query "how does the Streamlit UI call PyFLASH services" --graph graphify-out/graph.json`
- `python -m graphify query "plotting functions and action wrappers" --graph graphify-out/graph.json`

The graph is intentionally rebuilt from AST only over `PyFLASH/` and `tests/`.
Do not run full semantic graphify extraction for this project unless the user
explicitly asks. After significant code changes, rebuild it with:

```bash
python scripts/rebuild_graphify_ast.py
```

Post-commit and post-checkout git hooks also run the same AST-only rebuild. If
query results look stale, empty, or fail, run the script above, then fall back
to `rg` and report the stale graph.

## Development

Install locally with:

```bash
pip install -e .
```

Use the UI extra when working on Streamlit screens:

```bash
pip install -e ".[ui]"
pyflash-ui
```

Equivalent UI launch:

```bash
python -m streamlit run PyFLASH/ui/app.py
```

Run tests with:

```bash
pytest tests -q
```

For focused UI work, start with `pytest tests/test_ui_services.py -q` plus the
page-specific UI test file.

## Code Orientation

- Core import surface: `PyFLASH/__init__.py` lazily exposes heavy modules.
- Experiment import and summary building: `PyFLASH/experiment.py`.
- Multi-experiment orchestration and export methods: `PyFLASH/batch.py`.
- High-level batch factory and pickle caching: `PyFLASH/factory.py`.
- Conditions DSL and crossed designs: `PyFLASH/conditions.py`.
- Plotting wrappers and action functions: `PyFLASH/plotting.py`.
- Plot spec parsing: `PyFLASH/spec.py`.
- Streamlit-free UI adapter layer: `PyFLASH/ui/services.py`.
- UI project JSON schema and condition rebuild: `PyFLASH/ui/project_io.py`.
- Streamlit entry point and pages: `PyFLASH/ui/app.py`, `PyFLASH/ui/pages/`.

Keep `PyFLASH.ui.services` free of top-level `streamlit` imports. Core
`import PyFLASH` should not pull in Streamlit or plotting dependencies.

## Local Outputs

Do not commit local analysis outputs or generated graph artifacts:
`No Combo/`, `Results/`, `Exports/`, notebooks with private paths, and
`graphify-out/`.
