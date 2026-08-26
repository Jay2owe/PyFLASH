# PyFLASH - Agent Guide

PyFLASH is a Python package for processing and analyzing immunofluorescence
confocal microscopy data exported from FLASH/ImageJ workflows. The PyPI
distribution is `PyFLASH-analysis`; the import package is `PyFLASH`.

## AI Control Layer (drive PyFLASH in plain English)

PyFLASH has an agentify-pattern control layer so an agent can make any plot from a
natural-language request, and extend the package when a request needs a plot that
doesn't exist yet. Eight layers:

1. **Registry** — `PyFLASH/spec.py::PLOT_REGISTRY` (YAML short-name → `plot_*`),
   with `PyFLASH/param_docs.py` supplying what a signature cannot say. Declared
   entries carry units and meanings for the ~90 arguments that recur across the
   registry; everything else is derived from the live signature by
   `param_docs.describe_all`, so a new argument is documented the moment it
   exists. `describe` and the generated reference both read from there.
2. **Runner** — `~/.claude/skills/pyflash/scripts/pyflash_runner.py` (global, runnable
   from any directory): a thin JSON CLI
   (`submit`/`run`/`inspect`/`discover`/`script`/`status`/`shutdown`). Dispatches to any
   `plot_*` in `PyFLASH.plotting` by name; keeps the 288 MB `batch1.pkl` cached in a
   resident worker. Always returns the `equivalent_script`.
   Registry aliases may also point to module-qualified pipeline callables such as
   `PyFLASH.pipeline.adjusted_correlation`; the runner resolves those through
   `PyFLASH.spec.PLOT_REGISTRY`.
3. **Control skill** — `~/.claude/skills/pyflash/` (`SKILL.md` + `references/*.md`): the
   loop that turns a request into a call, runs it, shows the PNG preview, prints the code.
   Drive it with **`/pyflash`**.
4. **Reference refresh hook** — `.claude/settings.json` runs
   `python scripts/update_pyflash_references.py --if-needed --quiet` after Claude
   write/edit tools. The script refreshes the generated live-signature block in
   `~/.claude/skills/pyflash/references/plot-functions.md`. There is no longer a Codex
   mirror to keep in step: `~/.codex/skills` and `~/.claude/skills` are the same shared
   folder, and `.codex/skills/pyflash/references/` is a junction into it. Agents still
   maintain the hand-written teaching prose and catalog rows.
5. **Self-extension skill** — `.claude/skills/pyflash-extend/`: how to add a capability
   when `/pyflash` can't (register/document an existing function, or add a new `plot_*`).
   Use **`/pyflash-extend`**. The detailed plot-implementation contract lives in the global
   `pyflash-add-plot` skill.
6. **Orientation** — this section.
7. **Describe layer** — `PyFLASH/report.py`: a guarded, opt-in collector that captures the
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
8. **Montage layer** — `PyFLASH/pipeline_montage.py`: every analysis pipeline run writes,
   on top of its many individual figures, one **overview montage** —
   `! Overview Montage.png` (the `!` sorts it to the top of the run's `fig_dir`; the name
   is `Config.MONTAGE_FILENAME`, resolved at run time, so a user can override or restore the
   old `00 - Overview Montage` without a code edit) — tiling the run's
   most important graphs (coefficient + gate matrices, raw/adjusted matrices, missingness +
   covariation maps, and the top regression scatter plots). Mechanism mirrors the describe
   layer: an opt-in, inert-by-default capture collector taps `utils.save_fig` (the single
   figure choke point) via an observer; figures flagged `save_fig(..., montage=True)` are the
   headline panels, and a `capture_secondary(...)` block lets a pipeline pull its regressions
   onto the montage while leaving p/q-value matrices off. The `@montage_pipeline` decorator
   wraps each pipeline, builds the montage into `fig_dir`, and records `result["montage"]`;
   it honours the per-call `montage=` toggle and `save=False`. A specificity *queue* is one
   merged run sharing a single folder (each condition's outputs distinguished by a concise
   filename tag, e.g. `_Dx.AD`), so it gets one combined montage spanning all conditions.
   **Uniformity is enforced, not hoped for:** every name
   in `pipeline.__all__` must wear `@montage_pipeline` (or be in `pipeline.MONTAGE_EXEMPT`) —
   `tests/test_pipeline_montage.py` fails until it does. When you add a pipeline, give it a
   `montage=True` parameter, wear the decorator, and tag its headline `save_fig` calls.

`discover` is the source of truth for "what plots exist" — the generated reference block
self-heals against it through `scripts/update_pyflash_references.py`.

## PyFLASH owns its own style, and stands alone

**PyFLASH must stay installable by someone who has never heard of this lab.** It
is published — PyPI as `PyFLASH-analysis`, BSD-3, a readthedocs site — so it
imports nothing from `analysis-kit`, the internal shared package. The kit is an
optional `agent` extra because the `/pyflash` *skill* needs it; the *package*
never does. Adding a hard dependency on an unpublished package breaks
`pip install` for every outside user, silently and completely.

- **`PyFLASH/palette.py` is the only module allowed to write a hex literal.**
  Four tables: `HOUSE` (figure furniture), `PIPELINE` (the saturated palette a
  condition is named from, exposed as `Config.COLORS`), `AUTO` (Okabe-Ito,
  colourblind-safe, for a condition nobody named), and whatever the project
  declares at run time.
- **A project overrides the house rules for its conditions**, not for the
  figure: `palette.declare_conditions(WT="teal", KO="#ff00aa")` then
  `condition_colour("WT")`. Reachable only through `condition_colour`, so a
  condition named `black` cannot repaint every axis label.
- **Lookup order differs on purpose.** `colour("red")` is the muted house red;
  `condition_colour("red")` is the loud pipeline red, because that is what
  `condition(..., color="red")` has always meant. Four names collide — `red`,
  `orange`, `blue`, `black` — and `palette._CONDITION_ORDER` is why they can.
- **A pickled condition's colour must never move. This outranks everything
  else in this section.** A condition's colour is resolved once, when the
  condition is built, and pickled onto the object. Across Jamie's five batches,
  26 of 27 are frozen `#rrggbb` and no palette change can reach them — but
  `CK1I.pkl` stores the *name* `"black"`, and a name is re-resolved every time
  that batch is plotted. So the rule is not "never change the palette"; it is
  **a name a pickle may hold must always resolve to the value it had when that
  pickle was written**. `PICKLED_CONDITION_COLOURS` in
  `tests/test_style_conformance.py` pins the whole `PIPELINE` table by value,
  one test per name, and asserts the house palette can never capture a name out
  from under it. Do not "tidy" `PIPELINE`.
- **`tests/test_style_conformance.py` pins PyFLASH to the shared kit** where the
  kit is installed, and skips cleanly where it is not. Two copies of a palette
  drift; that test is what makes the copy safe.
- `plotting.py` still holds ~109 per-plot decoration colours. They are
  deliberately not swept — a bulk substitution inside f-strings is its own job
  with its own regression risk, and the conformance test's scope says so.
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
- Per-run overview montage (`@montage_pipeline` decorator, `save_fig`-tap capture
  collector, `build_montage` grid builder): `PyFLASH/pipeline_montage.py`. Every
  `pipeline.__all__` entry must wear the decorator or be `MONTAGE_EXEMPT`
  (`tests/test_pipeline_montage.py` enforces it).
- Outlier detection (`flag_outliers`, `iqr_bounds`, `mad_modified_z`), effect
  sizes, FDR, ICC: `PyFLASH/stats_extra.py`.
- Outlier / manual exclusion for downstream analysis (`exclude_outliers`,
  `mark_outliers`, `exclude_animals`, `mark_animals`, `apply_exclusions`,
  `mark_exclusions`): `PyFLASH/exclusions.py`. Returns a non-destructive cleaned
  shallow copy of the experiment whose flagged cells/rows hold a reason-coded
  `EXCLUDED_` sentinel — `EXCLUDED_OUTLIER:<rule>` (auto) or
  `EXCLUDED_MANUAL:<reason>` (user-supplied via `exclude_animals(..., reason=)`).
  Both are treated as analysis-missing by every coercion path (the `EXCLUDED_`
  family + `NOT_INCLUDED_IN_EXPERIMENT` are matched in `utils.is_excluded_mask`
  and `modelling._sentinel_like_mask`), counted separately from NaN in QC, plus an
  audit `.exclusions` ledger (animal, column, original value, kind, reason). The
  original is never mutated.
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

## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `python3 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"` to keep the graph current
