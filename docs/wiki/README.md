# PyFLASH Wiki

This wiki is the long-form PyFLASH reference. It explains objects, tables,
parameters, plots, pipelines, statistics, outputs, workflows, and examples.

## Start Here

| Page | Purpose |
|---|---|
| [Getting started](getting-started/README.md) | Short path through installation, first data object, first plot, UI launch, and outputs. |
| [Installation](getting-started/installation.md) | Install the package and optional UI extra. |
| [First batch](getting-started/first-batch.md) | Create or load a `Batch` from experiment folders. |
| [First table-backed batch](getting-started/first-table-batch.md) | Use a prepared `pandas.DataFrame`. |
| [First plot](getting-started/first-plot.md) | Make a basic plot. |
| [First plot spec](getting-started/first-plot-spec.md) | Run plots from YAML, TOML, or JSON. |
| [Launch the UI](getting-started/launch-the-ui.md) | Start the optional Streamlit interface. |
| [Where results go](getting-started/where-results-go.md) | Find saved figures and run folders. |

## Main Reference

| Page | Purpose |
|---|---|
| [API reference](api-reference.md) | Public functions grouped by task. |
| [Object model](object-model.md) | Short overview of the main objects. |
| [Object types](object-types/README.md) | Detailed object pages. |
| [Data structures](data-structures/README.md) | Tables, specs, ledgers, and manifests. |
| [Parameters](parameters/README.md) | Shared option vocabulary. |
| [Plot types](plot-types/README.md) | Visual guide to plot families. |
| [Statistics](statistics/README.md) | Method and interpretation guides. |
| [Outputs](outputs/README.md) | Saved files and folders. |
| [Workflows](workflows/README.md) | Task-based guides. |
| [Gallery](gallery/README.md) | Compact examples. |
| [Plot gallery](gallery/plot-gallery.md) | Rendered example of every plot, linked to its reference page. |
| [Troubleshooting](troubleshooting/README.md) | Common problems and fixes. |
| [Glossary](glossary/README.md) | Short definitions. |
| [Developer docs](developer/README.md) | Maintainer guidance. |

## Naming Convention

Preferred public names are `data_cols`, `group`, `groupList`, `group_col`,
`group_cols`, `subject_col`, `filter_by`, and `split_by`. Legacy names such as
`filtered_columns`, `conditionList`, `condition_col`, `factor_cols`,
`animal_col`, `specificity`, and `factor` remain supported.
