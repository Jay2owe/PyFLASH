# Plot Registry

## Summary

`PyFLASH/spec.py::PLOT_REGISTRY` is the single dictionary that maps a short
plot name (the string a user writes in a YAML/TOML/JSON spec, or hands the
`/pyflash` runner) to the callable that draws it. Spec validation, the
natural-language runner, and the generated skill reference are all built on this
one table, so registering a plot here is what makes it "exist" to the whole
control layer.

## Short Names vs Callable Names

Keys are short names (`'mean_bars'`, `'regressions'`, `'volcano'`). Values are
resolved by `spec._resolve_func`:

- A bare value like `'plot_mean_bars'` is looked up as an attribute of
  `PyFLASH.plotting`.
- A dotted value like `'PyFLASH.pipeline.adjusted_correlation'` is imported by
  module path and attribute. This is how pipeline callables and
  `'iterative_model_sweep' -> 'PyFLASH.modelling.iterative_model_sweep'` are
  registered — the registry is not limited to `plot_*` functions in the
  plotting module.

So the same registry drives both plain plots and full analysis pipelines; the
runner resolves either through `PLOT_REGISTRY` without special-casing.

## The Runner Is Dumb — No Runner Edit Needed

The runner dispatches to any `plot_*` in `PyFLASH.plotting` by name and resolves
registered aliases through `PLOT_REGISTRY`. A new `plot_*` function is therefore
callable the moment it is defined; you edit `PLOT_REGISTRY` only to give it a
short-name alias, spec validation, and reference-block coverage. Never add plot
dispatch logic to the runner.

## Describe-Coverage Classification (Enforced)

Every key in `PLOT_REGISTRY` must appear in exactly one of three sets in
`spec.py`:

- `DESCRIBE_COVERED` — emits structured records into `PyFLASH.report` (via the
  shared stats engine, a direct `report.emit`, or a pipeline return manifest).
- `DESCRIBE_EXEMPT` — a pure/descriptive visualisation with no inferential
  result to capture.
- `DESCRIBE_UNREVIEWED` — computes an inferential result that is not yet wired
  into the report layer (a tracked backlog).

`spec.describe_status(short_name)` returns `covered` / `exempt` / `unreviewed`
or `unclassified`. `tests/test_describe_coverage.py` **fails** until every
registered short-name is classified, and also fails if a classified name is not
in the registry or if the three sets overlap. The runner's `discover` command
surfaces `describe_coverage`.

## See Also

- [Adding A Plot](adding-a-plot.md)
- [Structured Results](structured-results.md)
- [Testing Map](testing-map.md)
- [Plot spec files](../data-structures/plot-spec-files.md)
- [API reference](../api-reference.md)
