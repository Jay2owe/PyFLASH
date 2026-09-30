# PyFLASH agent context

This is the portable, read-only orientation guide for the PyFLASH Python package.

Package version: `0.3.0`

Use this file when an agent cannot import the package or run its local command-line interface (CLI). The structured companion is [`pyflash_context.json`](pyflash_context.json).

## Public context interface

```python
from PyFLASH import context
context.read(format='json')
context.read('plotting', format='json')
context.search('missing column')
```

Non-CLI clients should read the relevant topic below or the structured JSON bundle. These artifacts explain usage; they do not execute plots or expose user data.

## Topic index

- `overview` - Choose a PyFLASH workflow
- `data` - Load and describe experiment data
- `plotting` - Choose a registered plot
- `analysis` - Run a statistical or pipeline analysis
- `outputs` - Read and preserve outputs
- `troubleshooting` - Diagnose a rejected or unexpected call

## Topics

### Choose a PyFLASH workflow

Topic key: `overview`

```text
PyFLASH 0.3.0 - Choose a PyFLASH workflow

PyFLASH is a Python package for turning microscopy experiment data into analysed tables and figures. Its public plotting and analysis functions are the callable surface. The package's live plot registry is `PyFLASH.spec.PLOT_REGISTRY`; the agent runner resolves those names and returns JSON plus an equivalent script. Start by identifying the batch, the question, and the output folder.
```

### Load and describe experiment data

Topic key: `data`

```text
PyFLASH 0.3.0 - Load and describe experiment data

A normal workflow starts from a `Batch` created with `PyFLASH.create_batch(...)` or loaded with `PyFLASH.load_state(...)`. Keep the input state unchanged while exploring a plot. For a new request, identify the batch path, its conditions and the grouping or filtering needed; do not guess column names when `data_overview` or the runner's live descriptions can establish them.
```

### Choose a registered plot

Topic key: `plotting`

```text
PyFLASH 0.3.0 - Choose a registered plot

Use the `/pyflash` control skill or its runner to discover registered aliases and inspect their live signatures. The runner accepts an action name plus JSON parameters; it can produce SVG outputs and PNG previews. Prefer a registered plot whose name and reference entry match the question. Shared parameters such as filters, markers, grouping and output location retain the same meaning across plots.
```

### Run a statistical or pipeline analysis

Topic key: `analysis`

```text
PyFLASH 0.3.0 - Run a statistical or pipeline analysis

PyFLASH exposes pipeline and modelling callables such as `data_overview`, `correlation`, `adjusted_correlation`, `linear_model`, and `rhythm`. Choose the analysis from the scientific question, preserve the returned evidence and inspect missing or unsupported estimates. The action layer is the stable boundary for agent calls; it does not replace the package's statistical definitions.
```

### Read and preserve outputs

Topic key: `outputs`

```text
PyFLASH 0.3.0 - Read and preserve outputs

Write outputs under the request's explicit result root. A successful runner response includes structured results, output paths when applicable, provenance or run metadata, and an `equivalent_script`. Treat the script and recorded inputs as part of the result so another agent can reproduce the call. A preview is for inspection; the SVG or data artifact is the durable output.
```

### Diagnose a rejected or unexpected call

Topic key: `troubleshooting`

```text
PyFLASH 0.3.0 - Diagnose a rejected or unexpected call

For an unknown action, run live `discover` and then `describe` the exact alias. For a parameter error, use the live signature and the package reference rather than inventing a spelling. If a figure has the wrong appearance, check the active PyFLASH style, filters, grouping and output metadata before rerunning. A failed call may have created files; inspect the result root before repeating a write.
```

## Machine-readable metadata

The JSON companion contains the package version, reader contract and every public topic. It is read-only orientation data.
