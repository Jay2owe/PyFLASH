# Testing Map

## Summary

Which tests in `tests/` protect which subsystem. Use this to find the right
focused test before editing, and to know which enforcement test will fail if you
skip a maintenance step. Run the whole suite with `pytest tests -q`, or a single
file with `pytest tests/<file>.py -q`. The rows below use real filenames present
in `tests/`.

## Subsystem → Tests

| Subsystem | Tests |
|---|---|
| Loading, factory, lazy import surface | `test_init_lazy_attrs.py`, `test_serialization_legacy_imports.py`, `test_experiment_new_imagej_layout.py`, `test_miniexperiment.py`, `test_dataframe_adapter.py` |
| Registry + describe coverage (enforcement) | `test_describe_coverage.py` |
| Report / describe collector | `test_report.py` |
| Pipeline montage (enforcement + behaviour) | `test_pipeline_montage.py` |
| Correlation pipelines | `test_correlation_pipeline.py`, `test_adjusted_correlation_pipeline.py` |
| Data overview pipeline | `test_overview_pipeline.py` |
| Group comparison + linear model pipelines | `test_group_comparison_pipeline.py`, `test_linear_model_pipeline.py` |
| Modelling / iterative model sweep | `test_iterative_model_sweep_outputs.py` |
| Rhythm module | `test_rhythm.py` |
| Plotting (correlation methods, labels, radar, matrix) | `test_plotting_correlation_methods.py`, `test_plotting_display_names.py`, `test_plotting_radar.py`, `test_multivariable_regression_matrix.py` |
| Standalone group-comparison plots (superplot / effect forest / group matrix) | `test_standalone_group_plots.py` |
| Representative images | `test_representative_image_outputs.py` |
| Statistics (extra stats, effect sizes, outliers, annotations) | `test_stats_extra.py`, `test_stats_annotations.py` |
| Exclusions / outlier marking | `test_exclusions.py` |
| Conditions + style channel | `test_condition_styles.py`, `test_ui_conditions.py` |
| Summary export edge cases | `test_unregistered_summary_export.py` |
| UI services boundary (Streamlit-free) | `test_ui_services.py` |
| UI pages | `test_ui_plots.py`, `test_ui_images.py`, `test_ui_conditions.py` |

## The Enforcement Tests

Three tests are forcing functions — they fail on a maintenance omission, not a
code bug:

- `test_describe_coverage.py` — every `PLOT_REGISTRY` short-name must be
  classified in one of the `DESCRIBE_*` sets in `spec.py`, the sets must be
  disjoint, and no classified name may be absent from the registry.
- `test_pipeline_montage.py::test_every_pipeline_is_montage_enforced` — every
  name in `pipeline.__all__` must wear `@montage_pipeline` or be in
  `pipeline.MONTAGE_EXEMPT`; its companion asserts each enforced pipeline exposes
  `montage=` and `save=` parameters.
- `test_ui_services.py` — asserts importing `PyFLASH.ui.services` does not pull
  in `streamlit` and that core `import PyFLASH` stays clean.

## See Also

- [Plot Registry](plot-registry.md)
- [Adding A Plot](adding-a-plot.md)
- [Structured Results](structured-results.md)
- [UI Services](ui-services.md)
