# Troubleshooting

Use these pages when PyFLASH imports, loads data, builds groups, saves plots,
or runs statistics in a way you did not expect. Each page starts with practical
fixes, then lists symptoms, likely causes, checks, and related reference pages.

## Fast Checks

- Confirm you are using the same Python environment for install, UI launch, and scripts.
- Inspect the object you are passing: most plotting functions need a `Batch`,
  `Experiment`, `MiniExperiment`, or a DataFrame-shaped input documented for that function.
- Print the raw column names before selecting data columns:
  `list(batch.summary.columns)`.
- Check whether a plot was run with `save=False`; that returns or displays a figure
  but does not write an SVG.
- For moved pickles, load with path normalization before re-running plots:
  `load_state("path/to/file.pkl")`.
- For spec files, validate the plot `type` against `available_plots()`.

## Problems

| Problem | Start here |
| --- | --- |
| Python cannot import PyFLASH or optional UI/spec/image packages | [Import errors](import-errors.md) |
| Pickles load but paths point to the old computer or folder | [Moved pickles](moved-pickles.md) |
| A plot says columns are missing or no numeric columns remain | [Missing columns](missing-columns.md) |
| Groups, factors, or comparisons do not match the data | [Group labels do not match](conditions-do-not-match.md) |
| A plot ran but no file appeared | [No plots saved](no-plots-saved.md) |
| Image grids or representative panels do not load | [Image loading](image-loading.md) |
| A YAML, TOML, or JSON plot spec does not run | [Invalid plot spec](invalid-plot-spec.md) |
| The Streamlit UI does not launch or cannot see data | [UI problems](ui-problems.md) |
| `iterative_model_sweep` is too slow | [Slow model sweeps](slow-model-sweeps.md) |
| P values, model outputs, or group comparisons look wrong | [Statistics look wrong](statistics-look-wrong.md) |

## Related Pages

- [Getting started](../getting-started/README.md)
- [Object model](../object-model.md)
- [Parameters](../parameters/README.md)
- [Outputs](../outputs/README.md)
- [Glossary](../glossary/README.md)
