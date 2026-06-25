# PyFLASH - Agent Guide

PyFLASH is a Python package for processing and analyzing immunofluorescence
confocal microscopy data exported from FLASH/ImageJ workflows. The PyPI
distribution is `PyFLASH-analysis`; the import package is `PyFLASH`.

## AI Control Layer (drive PyFLASH in plain English)

PyFLASH has an agentify-pattern control layer so an agent can make any plot from a
natural-language request, and extend the package when a request needs a plot that
doesn't exist yet. Six layers:

1. **Registry** — `PyFLASH/spec.py::PLOT_REGISTRY` (YAML short-name → `plot_*`).
2. **Runner** — `.claude/skills/pyflash/scripts/pyflash_runner.py`: a thin JSON CLI
   (`submit`/`run`/`inspect`/`discover`/`script`/`status`/`shutdown`). Dispatches to any
   `plot_*` in `PyFLASH.plotting` by name; keeps the 288 MB `batch1.pkl` cached in a
   resident worker. Always returns the `equivalent_script`.
   Registry aliases may also point to module-qualified pipeline callables such as
   `PyFLASH.pipeline.adjusted_correlation`; the runner resolves those through
   `PyFLASH.spec.PLOT_REGISTRY`.
3. **Control skill** — `.claude/skills/pyflash/` (`SKILL.md` + `reference/*.md`): the
   loop that turns a request into a call, runs it, shows the PNG preview, prints the code.
   Drive it with **`/pyflash`**.
4. **Self-extension skill** — `.claude/skills/pyflash-extend/`: how to add a capability
   when `/pyflash` can't (register/document an existing function, or add a new `plot_*`).
   Use **`/pyflash-extend`**. The detailed plot-implementation contract lives in the global
   `pyflash-add-plot` skill.
5. **Orientation** — this section.
6. **Describe layer** — `PyFLASH/report.py`: a guarded, opt-in collector that captures the
   descriptive + inferential numbers a plot already computes (per-group n/mean/SD by animal,
   test, p-values, effect sizes, correlation r/p) instead of discarding them. `stats.py`
   (`multipleComparisons`) and `plotting.py` (`regression_action`) emit into it when armed;
   pipeline callables are captured via their return manifest. The runner arms it per run and
   persists a per-run JSON manifest (Tier 1) + deterministic markdown digest (Tier 2) +
   append-only `index.jsonl` ledger to `.runtime/results_store/`, plus a `lab_notebook.md`
   for agent interpretations (Tier 3). This lets an agent answer questions and build
   cross-run storytelling from structured facts rather than re-reading PNGs. Drive the
   rundown via the runner's `runs`/`result`/`note` subcommands (see the `/pyflash` skill).
   The collector is inert unless armed, so core plotting is unchanged.
   **Coverage is enforced, not hoped for:** every `PLOT_REGISTRY` entry must be classified
   in `spec.py` as `DESCRIBE_COVERED` / `DESCRIBE_EXEMPT` / `DESCRIBE_UNREVIEWED`
   (`tests/test_describe_coverage.py` fails until it is), `discover` reports
   `describe_coverage`, and a 0-record non-exempt run returns a `describe_note`. When you
   add a plot that computes statistics, emit them (shared engine or `report.emit`) and mark
   it `DESCRIBE_COVERED` — see the `pyflash-add-plot` skill's describe-layer contract.

`discover` is the source of truth for "what plots exist" — the docs self-heal against it.
Keep the registry in the package and the runner dumb; new `plot_*` functions are usable the
moment they exist, no runner edit.
Registered pipeline callables are supported the same way through `PLOT_REGISTRY`.

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
- High-level analysis pipelines (`correlation` / `adjusted_correlation` /
  `data_overview`): `PyFLASH/pipeline.py`.
- Shared pipeline run-folder / manifest IO (one `run_dirs`/`slug`/
  `append_runs_index` for every pipeline): `PyFLASH/pipeline_io.py`.
- Outlier detection (`flag_outliers`, `iqr_bounds`, `mad_modified_z`), effect
  sizes, FDR, ICC: `PyFLASH/stats_extra.py`.
- Outlier exclusion / marking for downstream analysis (`exclude_outliers`,
  `mark_outliers`, `apply_exclusions`): `PyFLASH/exclusions.py`. Returns a
  non-destructive cleaned shallow copy of the experiment whose flagged cells hold
  the reason-coded `EXCLUDED_OUTLIER` sentinel (treated as analysis-missing by
  every coercion path, counted separately from NaN in QC), plus an audit
  `.exclusions` ledger. The original is never mutated.
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
