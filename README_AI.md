# PyFLASH agent guide

Package version: `0.3.1`

Read-only usage guide generated from the package's public context module.

Structured companion: `PyFLASH_context.json`.

## Reader

```python
from PyFLASH import context; context.read(format='json')
```

## Choose a PyFLASH workflow (`overview`)

```markdown
PyFLASH 0.3.1 - Choose a PyFLASH workflow

PyFLASH is a Python package for turning microscopy experiment data into analysed tables and figures. Its public plotting and analysis functions are the callable surface. The package's live plot registry is `PyFLASH.spec.PLOT_REGISTRY`; the agent runner resolves those names and returns JSON plus an equivalent script. Start by identifying the batch, the question, and the output folder.
```

## Load and describe experiment data (`data`)

```markdown
PyFLASH 0.3.1 - Load and describe experiment data

A normal workflow starts from a `Batch` created with `PyFLASH.create_batch(...)` or loaded with `PyFLASH.load_state(...)`. Keep the input state unchanged while exploring a plot. For a new request, identify the batch path, its conditions and the grouping or filtering needed; do not guess column names when `data_overview` or the runner's live descriptions can establish them.
```

## Choose a registered plot (`plotting`)

```markdown
PyFLASH 0.3.1 - Choose a registered plot

Use the `/pyflash` control skill or its runner to discover registered aliases and inspect their live signatures. The runner accepts an action name plus JSON parameters; it can produce SVG outputs and PNG previews. Prefer a registered plot whose name and reference entry match the question. Shared parameters such as filters, markers, grouping and output location retain the same meaning across plots.
```

## Run a statistical or pipeline analysis (`analysis`)

```markdown
PyFLASH 0.3.1 - Run a statistical or pipeline analysis

PyFLASH exposes pipeline and modelling callables such as `data_overview`, `correlation`, `adjusted_correlation`, `linear_model`, and `rhythm`. Choose the analysis from the scientific question, preserve the returned evidence and inspect missing or unsupported estimates. The action layer is the stable boundary for agent calls; it does not replace the package's statistical definitions.
```

## Read and preserve outputs (`outputs`)

```markdown
PyFLASH 0.3.1 - Read and preserve outputs

Write outputs under the request's explicit result root. A successful runner response includes structured results, output paths when applicable, provenance or run metadata, and an `equivalent_script`. Treat the script and recorded inputs as part of the result so another agent can reproduce the call. A preview is for inspection; the SVG or data artifact is the durable output.
```

## Use the shared API, command line and browser controls (`control`)

```markdown
PyFLASH 0.3.1 - Use the shared API, command line and browser controls

`pyflash-control describe <action>` reads the same parameter keys, labels, help, units and choices as the browser workbench. `pyflash-control run <action> --input <csv-or-pickle> --params <JSON> --output <new-folder>` retains input/output hashes, software versions, configuration, code identity and an equivalent standalone script. Source-free helpers omit --input. Plot appearance is a separate --style JSON object; its `presentation` mapping edits ranges, legends, series colours, stroke widths and fonts without changing measurements. Each function's browser appearance and comparison choices are saved with the workspace. `PyFLASH.queue.run_action_grid` streams bounded comparison cells, verifies content before reuse and keeps immutable failed/retried attempt records. `pyflash-control queue --input <data> --spec <recipe> --progress <progress.json>` resumes verified completed calls and records a new receipt/script for each invocation. Browser failures also retain a replay script and their original error; old completed exports retain their own scripts regardless of the newest job. Use `pyflash-control doctor` or the point-of-use browser repair control to inspect declared optional dependencies.
```

## Diagnose a rejected or unexpected call (`troubleshooting`)

```markdown
PyFLASH 0.3.1 - Diagnose a rejected or unexpected call

For an unknown action, run live `discover` and then `describe` the exact alias. For a parameter error, use the live signature and the package reference rather than inventing a spelling. If a figure has the wrong appearance, check the active PyFLASH style, filters, grouping and output metadata before rerunning. A failed call may have created files; inspect the result root before repeating a write.
```
