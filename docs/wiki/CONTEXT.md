# Wiki Context

This wiki is the long-form PyFLASH reference. Future agents should use it to
expand user-facing documentation without losing the conventions already started
in this folder.

## Current Style

- The target style is close to Matplotlib documentation.
- Explain the library vocabulary, object types, data structures, common
  parameters, plot families, statistical outputs, and saved files as first-class
  reference material.
- Explain the purpose in plain language before implementation detail.
- Prefer concrete examples using real `PyFLASH` imports.
- Keep function pages focused on one callable.
- Put shared concepts in concept pages and link to them from function pages.
- Separate Python return values from files saved to disk.

Read these first:

- [README](README.md) for the wiki entry point and coverage plan.
- [Documentation standard](documentation-standard.md) for function page shape.
- [API reference](api-reference.md) for the public API grouping.
- [Object model](object-model.md) for the main objects users pass around.

## Folder Map

| Folder | Purpose |
|---|---|
| `functions/` | One detailed page per public callable, including object compatibility, parameters, returns, saved outputs, examples, notes, and related functions. |
| `getting-started/` | First-contact onboarding pages for installation, first batches, first plots, specs, UI launch, and where results go. |
| `object-types/` | Detailed pages for Python object types such as `Batch`, `Experiment`, `MiniExperiment`, `DataFrameExperiment`, conditions, markers, and config. |
| `data-structures/` | Tables, file formats, schemas, specs, ledgers, and manifests used inside object types and outputs. |
| `plot-types/` | Visual guide to plot families, when to use them, and which function pages implement them. |
| `parameters/` | Common parameter and option vocabularies shared by many functions. |
| `statistics/` | Method and interpretation guides for tests, corrections, effect sizes, models, rhythm, and structured results. |
| `outputs/` | Saved figures, folders, workbooks, pickle files, pipeline outputs, and report records. |
| `gallery/` | Compact example pages with code and rendered or summarized results. |
| `glossary/` | Short searchable definitions of PyFLASH, microscopy, plotting, statistics, and parameter terms. |
| `troubleshooting/` | Problem-solving pages for common errors, surprising outputs, slow runs, and setup issues. |
| `concepts/` | Cross-cutting explanations that do not fit a more specific reference section. |
| `workflows/` | Task-based guides that show users how to get from an input state to a result, such as creating a batch, building groups, running a pipeline, exporting tables, or using the UI. |
| `developer/` | Maintainer-facing notes for future code and documentation work, such as registry behavior, UI service boundaries, project files, testing expectations, and adding new plots. |

Root-level pages should stay limited to wiki entry points and cross-cutting
indexes. If a root page grows into a family of pages, create or use a subfolder
and leave a short index page at the root.

## Sources Of Truth

Use source code and tests instead of guessing:

- Public import surface: `PyFLASH/__init__.py`
- Plot and pipeline registry: `PyFLASH/spec.py::PLOT_REGISTRY`
- Object model and import behavior: `PyFLASH/experiment.py`, `PyFLASH/batch.py`,
  `PyFLASH/factory.py`, `PyFLASH/dataframe.py`
- Conditions: `PyFLASH/conditions.py`
- Plotting wrappers and plot actions: `PyFLASH/plotting.py`
- Pipeline behavior: `PyFLASH/pipeline.py`, `PyFLASH/pipeline_io.py`,
  `PyFLASH/pipeline_montage.py`
- Modelling: `PyFLASH/modelling.py`
- Exclusions: `PyFLASH/exclusions.py`
- UI adapter layer: `PyFLASH/ui/services.py`, `PyFLASH/ui/project_io.py`
- Tests: `tests/`

For architecture questions, query the local graph first as described in the
project `AGENTS.md`, then fall back to targeted source reads.

## Expansion Workflow

1. Read this file, the relevant folder `CONTEXT.md`, and any existing nearby
   pages before writing.
2. Inspect the callable, object, or workflow in source code and tests.
3. Choose the most specific folder. For example, document `Batch` in
   `object-types/`, `data_cols` in `parameters/`, `batch.summary` in
   `data-structures/`, `plot_mean_bars` in `functions/`, a first-use path in
   `getting-started/`, and recurring errors in `troubleshooting/`.
4. Add or update the wiki page in the right folder.
5. Update [API reference](api-reference.md) when adding a new public function
   page.
6. Update [README](README.md) when adding a major entry-point page or changing
   the folder structure.
7. Keep examples copy-pasteable and use path placeholders instead of private
   local paths.

## What Not To Do

- Do not copy long blocks of implementation code into the wiki.
- Do not document private helpers unless they are necessary to explain public
  behavior.
- Do not move existing pages just to tidy the tree unless the user asks.
- Do not invent behavior from function names. Check the code and tests.
