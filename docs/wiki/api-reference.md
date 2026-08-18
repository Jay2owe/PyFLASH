# API Reference

This page groups the main public API surfaces. It is an index, not a replacement
for detailed function pages.

## Core Loading and Saving

| Object | Import | Purpose |
|---|---|---|
| `create_batch` | `from PyFLASH import create_batch` | Create or load a processed `Batch`. |
| `from_dataframe` | `from PyFLASH import from_dataframe` | Wrap already-tabular data in a PyFLASH-compatible object. |
| `DataFrameExperiment` | `from PyFLASH import DataFrameExperiment` | The object returned by `from_dataframe`. |
| `save_state` | `from PyFLASH import save_state` | Save a `Batch` or `Experiment` to pickle. |
| `load_state` | `from PyFLASH import load_state` | Load a saved pickle. |
| `normalize_paths` | `from PyFLASH import normalize_paths` | Rebase saved paths after moving data between machines. |

Detailed pages:

- [`create_batch`](functions/create_batch.md)
- [`from_dataframe`](functions/from_dataframe.md)

Several summary-first plotting and pipeline functions also accept a raw
`pandas.DataFrame` directly with `group_col=...`, `group_cols=...`, and
`subject_col=...`. They call `from_dataframe` internally. Legacy aliases such
as `condition_col`, `factor_cols`, and `animal_col` still work.

## Import Utilities

| Object | Import | Purpose |
|---|---|---|
| `resolve_experiment_paths` | `from PyFLASH.experiment import resolve_experiment_paths` | Resolve an experiment folder to its importable data folder and root. |
| `resolve_experiment_data_path` | `from PyFLASH.experiment import resolve_experiment_data_path` | Return the data folder for an experiment path. |
| `is_experiment_folder` | `from PyFLASH.experiment import is_experiment_folder` | Check whether a folder looks like an importable experiment. |

## Data Objects

| Object | Import | Purpose |
|---|---|---|
| `Batch` | `from PyFLASH import Batch` | Collection of experiments with a shared group list. |
| `Experiment` | `from PyFLASH import Experiment` | Full experiment folder import object. |
| `MiniExperiment` | `from PyFLASH import MiniExperiment` | Lightweight table-based experiment object. |
| `DataFrameExperiment` | `from PyFLASH import DataFrameExperiment` | In-memory object backed by user-supplied DataFrames. |
| `Antibody` | `from PyFLASH import Antibody` | Marker data class for antibody channels. |
| `cellMarker` | `from PyFLASH import cellMarker` | Marker data class for cell/object counters. |
| `objectMarker` | `from PyFLASH import objectMarker` | Marker data class for object-level measurements. |
| `Attribute` | `from PyFLASH import Attribute` | Generic attribute data class. |

See also: [Object model](object-model.md).

## Batch Export Methods

These are methods on a `Batch` object rather than top-level functions.

| Method | Purpose |
|---|---|
| `batch.export_all_excel()` | Write the standard formatted Excel outputs. |
| `batch.export_IF_summary_excel()` | Export the immunofluorescence summary workbook. |
| `batch.export_extended_data_excel()` | Export the extended immunofluorescence workbook. |
| `batch.export_behavior_summary_excel()` | Export behavior data when present. |
| `batch.export_extra_summary_excel()` | Export extra summary tables when present. |

## Groups

| Object | Import | Purpose |
|---|---|---|
| `GroupBuilder` | `from PyFLASH import GroupBuilder` | Preferred fluent builder for group lists. Classic alias: `ConditionBuilder`. |
| `group` | `from PyFLASH import group` | Single group object. Classic alias: `condition`. |
| `multiGroup` | `from PyFLASH import multiGroup` | Crossed group object. Classic alias: `multiCondition`. |
| `groupList` | `from PyFLASH import groupList` | Ordered group collection. Classic alias: `conditionList`. |
| `zipGroups` | `from PyFLASH import zipGroups` | Create groups from parallel lists. Classic alias: `zipConditions`. |
| `zipGroupLists` | `from PyFLASH import zipGroupLists` | Cross two group lists. Classic alias: `zipConditionLists`. |

The classic `ConditionBuilder`, `condition`, `multiCondition`, `conditionList`,
`zipConditions`, and `zipConditionLists` names remain supported.

## Pipeline Functions

| Function | Import | Purpose |
|---|---|---|
| `correlation` | `from PyFLASH import correlation` | Correlation discovery, significance gates, and regression plots. |
| `adjusted_correlation` | `from PyFLASH import adjusted_correlation` | Correlation analysis adjusted for covariates. |
| `data_overview` | `from PyFLASH import data_overview` | One-call descriptive overview and quality-control report. |
| `group_comparison` | `from PyFLASH import group_comparison` | Per-marker group comparisons with effect sizes and figures. |
| `linear_model` | `from PyFLASH import linear_model` | Adjusted linear-model pipeline with coefficients and adjusted means. |
| `rhythm` | `from PyFLASH import rhythm` | Cosinor and circular rhythm analysis. |

Detailed pages:

- [`correlation`](functions/correlation.md)
- [`adjusted_correlation`](functions/adjusted_correlation.md)
- [`data_overview`](functions/data_overview.md)
- [`group_comparison`](functions/group_comparison.md)
- [`linear_model`](functions/linear_model.md)
- [`rhythm`](functions/rhythm.md)

## Modelling Functions

| Function | Import | Purpose |
|---|---|---|
| `iterative_best_fit` | `from PyFLASH import iterative_best_fit` | Leave-one-out feature-subset search for linear regression. |
| `iterative_model_sweep` | `from PyFLASH import iterative_model_sweep` | Classifier and feature-subset sweep for categorical targets. |
| `run_linear_model_pipeline` | `from PyFLASH import run_linear_model_pipeline` | Compatibility wrapper for the original table-only linear-model workflow. |

Detailed pages:

- [`iterative_best_fit`](functions/iterative_best_fit.md)
- [`iterative_model_sweep`](functions/iterative_model_sweep.md)
- [`run_linear_model_pipeline`](functions/run_linear_model_pipeline.md)

## Plot Utilities

| Function | Import | Purpose |
|---|---|---|
| `get_display_name` | `from PyFLASH.plotting import get_display_name` | Convert raw summary column names to readable labels. |
| `set_display_name` | `from PyFLASH.plotting import set_display_name` | Apply readable labels to Matplotlib axes. |
| `set_axis_limits` | `from PyFLASH import set_axis_limits` | Store manual axis limits on an experiment or batch. |
| `clear_axis_limits` | `from PyFLASH import clear_axis_limits` | Remove stored axis limits. |
| `lock_axis_limits` | `from PyFLASH import lock_axis_limits` | Derive and store reusable axis limits from data. |
| `cheat_sheet` | `from PyFLASH import cheat_sheet` | Print plot parameter help from the live plotting signatures. |

## Plotting Registry

These names are available through `PyFLASH.spec.PLOT_REGISTRY`, the Streamlit UI
plot launcher, and plot spec files.

| Registry name | Callable | Purpose |
|---|---|---|
| `mean_bars` | `plot_mean_bars` | Bar charts with individual points and statistical comparisons. |
| `matrices` | `plot_matrices` | Correlation matrices. |
| `rect_matrices` | `plot_rect_matrices` | Rectangular correlation heatmaps. |
| `matrix_differences` | `plot_matrix_differences` | Compare correlation matrices between groups. |
| `regressions` | `plot_regressions` | Regression plots. |
| `multivariable_regression_matrix` | `plot_multivariable_regression_matrix` | Joint regression matrix heatmaps. |
| `model_result_matrix` | `plot_model_result_matrix` | Precomputed model-result matrix heatmaps. |
| `volcano` | `plot_volcano` | Effect-vs-significance plot. |
| `radar` | `plot_radar` | Radar/spider plot over selected summary columns. |
| `histograms` | `plot_histograms` | Marker-level histogram plots. |
| `ridgeline` | `plot_ridgeline` | Marker-level ridgeline density plots. |
| `ecdf` | `plot_ecdf` | Empirical cumulative distribution plots. |
| `pie_charts` | `plot_pie_charts` | Category distribution pies or related formats. |
| `combo_pies` | `plot_combo_pies` | Combo-family distribution plots. |
| `locations` | `plot_locations` | Spatial object location plots. |
| `images` | `plot_images` | Image grids. |
| `representative_images` | `plot_representative_images` | Representative image panels. |
| `scatter_3d` | `plot_scatter_3d` | 3D scatter plots. |
| `condition_key` | `plot_condition_key` | Standalone condition legend/key. |
| `coloc_upset` | `plot_coloc_upset` | Colocalisation intersection plots. |
| `coloc_sankey` | `plot_coloc_sankey` | Conditional branching/alluvial colocalisation plots. |
| `power_curve` | `plot_power_curve` | Statistical power vs sample size. |
| `marker_pca` | `plot_marker_pca` | PCA biplot of marker profiles. |
| `timecourse` | `plot_timecourse` | Timecourse or growth-curve plot. |
| `superplot` | `plot_superplot` | ROI-level points grouped by subject/sample. |
| `effect_forest` | `plot_effect_forest` | Effect-size forest plot. |
| `group_matrix` | `plot_group_matrix` | Group-vs-control effect matrix. |
| `cosinor` | `plot_cosinor` | Cosinor rhythm fit plot. |
| `acrophase_clock` | `plot_acrophase_clock` | Circular acrophase clock plot. |
| `correlation_pipeline` | `PyFLASH.pipeline.correlation` | Pipeline callable exposed through the registry. |
| `adjusted_correlation_pipeline` | `PyFLASH.pipeline.adjusted_correlation` | Adjusted correlation pipeline. |
| `data_overview_pipeline` | `PyFLASH.pipeline.data_overview` | Overview/QC pipeline. |
| `group_comparison_pipeline` | `PyFLASH.pipeline.group_comparison` | Group comparison pipeline. |
| `linear_model_pipeline` | `PyFLASH.pipeline.linear_model` | Adjusted linear-model pipeline. |
| `rhythm_pipeline` | `PyFLASH.pipeline.rhythm` | Rhythm pipeline. |
| `iterative_model_sweep` | `PyFLASH.modelling.iterative_model_sweep` | Classifier model sweep. |

Detailed pages:

- [`plot_mean_bars`](functions/plot_mean_bars.md)
- [`plot_histograms`](functions/plot_histograms.md)
- [`plot_ridgeline`](functions/plot_ridgeline.md)
- [`plot_ecdf`](functions/plot_ecdf.md)
- [`plot_superplot`](functions/plot_superplot.md)
- [`plot_effect_forest`](functions/plot_effect_forest.md)
- [`plot_group_matrix`](functions/plot_group_matrix.md)

## Declarative Specs

| Object | Import | Purpose |
|---|---|---|
| `PLOT_REGISTRY` | `from PyFLASH.spec import PLOT_REGISTRY` | Short-name registry that maps spec/UI plot names to callables. |
| `load_spec` | `from PyFLASH.spec import load_spec` | Load a YAML, TOML, or JSON plot specification. |
| `validate_spec` | `from PyFLASH.spec import validate_spec` | Validate a plot spec before running it. |
| `run_spec` | `from PyFLASH import run_spec` | Load, validate, and execute a plot spec. |
| `describe_status` | `from PyFLASH.spec import describe_status` | Report the documentation/status metadata for a registry name. |

## Exclusion Helpers

| Function | Import | Purpose |
|---|---|---|
| `exclude_outliers` | `from PyFLASH import exclude_outliers` | Detect outliers and return a cleaned copy for analysis. |
| `mark_outliers` | `from PyFLASH import mark_outliers` | Record detected outliers without changing data. |
| `apply_exclusions` | `from PyFLASH import apply_exclusions` | Apply manual exclusion rules to cells, subjects, or columns. |
| `mark_exclusions` | `from PyFLASH import mark_exclusions` | Record manual exclusions without changing data. |
| `exclude_subjects` | `from PyFLASH import exclude_subjects` | Manually exclude whole subjects/samples. |
| `mark_subjects` | `from PyFLASH import mark_subjects` | Record whole-subject exclusions without changing data. |
| `exclude_animals` | `from PyFLASH import exclude_animals` | Legacy alias for subject exclusion. |
| `mark_animals` | `from PyFLASH import mark_animals` | Legacy alias for subject exclusion marking. |

## Configuration and Output Control

| Object | Import | Purpose |
|---|---|---|
| `Config` | `from PyFLASH import Config` | Global thresholds, color maps, aliases, and project settings. |
| `Verbosity` | `from PyFLASH import Verbosity` | Output verbosity levels. |
| `set_verbosity` | `from PyFLASH import set_verbosity` | Set package output verbosity. |
| `silent` | `from PyFLASH import silent` | Context manager that suppresses package output. |
| `verbose` | `from PyFLASH import verbose` | Context manager that temporarily increases output detail. |
| `format_summary_for_display` | `from PyFLASH import format_summary_for_display` | Return a display-only summary table with readable labels. |

## Streamlit-Free UI Services

These live in `PyFLASH.ui.services`. They are intended for the Streamlit app and
tests, but are also useful for scripts.

| Function | Purpose |
|---|---|
| `open_pickle` / `save_pickle` | Load or save PyFLASH pickle files. |
| `package_info` | Return import and package smoke-test information. |
| `summary_table` | Prepare a summary table for display or download. |
| `batch_overview` | Return a structured overview of a loaded batch. |
| `validate_experiment_folder` | Check whether a folder looks importable. |
| `discover_experiments` | Validate immediate subfolders as experiments. |
| `build_conditions` / `preview_conditions` | Build and preview group lists from JSON-style specs. |
| `run_create_batch` | Run batch creation while capturing progress output. |
| `available_plots` | Return registered plot names. |
| `run_plot_spec` | Validate and execute a plot spec file. |
| `run_quick_plot` | Run one registered plot from form parameters. |
| `run_image_grid` / `run_representative_panels` / `run_locations` | UI adapters for image and spatial plotting. |
## Detailed Function Pages

| Function page |
|---|
| [adjusted_correlation](functions/adjusted_correlation.md) |
| [axis-limits](functions/axis-limits.md) |
| [condition-builder](functions/condition-builder.md) |
| [correlation](functions/correlation.md) |
| [create_batch](functions/create_batch.md) |
| [data_overview](functions/data_overview.md) |
| [exclusions](functions/exclusions.md) |
| [format_summary_for_display](functions/format_summary_for_display.md) |
| [from_dataframe](functions/from_dataframe.md) |
| [group_comparison](functions/group_comparison.md) |
| [iterative_best_fit](functions/iterative_best_fit.md) |
| [iterative_model_sweep](functions/iterative_model_sweep.md) |
| [linear_model](functions/linear_model.md) |
| [load_state](functions/load_state.md) |
| [normalize_paths](functions/normalize_paths.md) |
| [plot_acrophase_clock](functions/plot_acrophase_clock.md) |
| [plot_coloc_sankey](functions/plot_coloc_sankey.md) |
| [plot_coloc_upset](functions/plot_coloc_upset.md) |
| [plot_combo_pies](functions/plot_combo_pies.md) |
| [plot_condition_key](functions/plot_condition_key.md) |
| [plot_cosinor](functions/plot_cosinor.md) |
| [plot_ecdf](functions/plot_ecdf.md) |
| [plot_effect_forest](functions/plot_effect_forest.md) |
| [plot_group_matrix](functions/plot_group_matrix.md) |
| [plot_histograms](functions/plot_histograms.md) |
| [plot_images](functions/plot_images.md) |
| [plot_locations](functions/plot_locations.md) |
| [plot_marker_pca](functions/plot_marker_pca.md) |
| [plot_matrices](functions/plot_matrices.md) |
| [plot_matrix_differences](functions/plot_matrix_differences.md) |
| [plot_mean_bars](functions/plot_mean_bars.md) |
| [plot_model_result_matrix](functions/plot_model_result_matrix.md) |
| [plot_multivariable_regression_matrix](functions/plot_multivariable_regression_matrix.md) |
| [plot_pie_charts](functions/plot_pie_charts.md) |
| [plot_power_curve](functions/plot_power_curve.md) |
| [plot_radar](functions/plot_radar.md) |
| [plot_rect_matrices](functions/plot_rect_matrices.md) |
| [plot_regressions](functions/plot_regressions.md) |
| [plot_representative_images](functions/plot_representative_images.md) |
| [plot_ridgeline](functions/plot_ridgeline.md) |
| [plot_scatter_3d](functions/plot_scatter_3d.md) |
| [plot_superplot](functions/plot_superplot.md) |
| [plot_timecourse](functions/plot_timecourse.md) |
| [plot_volcano](functions/plot_volcano.md) |
| [rhythm](functions/rhythm.md) |
| [run_linear_model_pipeline](functions/run_linear_model_pipeline.md) |
| [run_spec](functions/run_spec.md) |
| [save_state](functions/save_state.md) |
