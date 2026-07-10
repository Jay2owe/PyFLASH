# Parameters

## data_cols

Preferred parameter for selecting exact data columns. See also:
[Column selection](../parameters/column-selection.md).

## filtered_columns

Legacy/internal alias for `data_cols` (exact column names). Prefer `data_cols`
in new code. See also: [Column selection](../parameters/column-selection.md).

## data_col_contains

Select columns whose names contain one or more text fragments. See also:
[Column selection](../parameters/column-selection.md).

## column_strings

Legacy/internal alias for `data_col_contains`. Case-sensitive substring
matching; prefer `data_col_contains`. See also:
[Column selection](../parameters/column-selection.md).

## data_col_regex

Select columns with a regular expression. See also:
[Column selection](../parameters/column-selection.md).

## regex_string

Legacy/internal alias for `data_col_regex` (a Python regular-expression string).
Prefer `data_col_regex`. See also:
[Column selection](../parameters/column-selection.md).

## data_col_exclude

Remove selected columns by text or pattern after inclusion. See also:
[Column selection](../parameters/column-selection.md).

## exclude

Legacy/internal alias for `data_col_exclude`. Removes columns whose names
contain any token; it does not remove rows. See also:
[Column selection](../parameters/column-selection.md).

## filter_by

Preferred row filter parameter. `specificity` is the legacy/internal alias. See
also: [Filter By and row filters](../parameters/specificity.md).

## specificity

Legacy row-filter parameter, not statistical specificity. See also:
[Filter By and row filters](../parameters/specificity.md).

## split_by

Parameter for splitting a plot by conditions or a factor column. See also:
[Groups and factors](../parameters/conditions-and-factors.md).

## factor

Legacy/internal parameter that panels an analysis by the levels of one factor
column, such as `Diagnosis` or `Sex`. Prefer `split_by` in new code. See also:
[Groups and factors](../parameters/conditions-and-factors.md).

## group

A grouping label in some pipeline and modelling functions. See also:
[Groups and factors](../parameters/conditions-and-factors.md).

## group_col

Preferred name for a single grouping column. See also:
[Groups and factors](../parameters/conditions-and-factors.md).

## condition_col

Legacy or input-facing name for a condition/group column. See also:
[from_dataframe](../functions/from_dataframe.md).

## group_cols

Preferred name for multiple grouping or factor columns. See also:
[Groups and factors](../parameters/conditions-and-factors.md).

## factor_cols

Alias for multiple factor columns in DataFrame inputs. See also:
[from_dataframe](../functions/from_dataframe.md).

## subject_col

Preferred name for the subject identifier column. See also:
[Summary table](../data-structures/summary-table.md).

## animal_col

Legacy alias for the subject identifier column. See also:
[from_dataframe](../functions/from_dataframe.md).

## comparisons

The requested group comparisons, usually resolved to index strings like `1-2`.
See also: [Groups and factors](../parameters/conditions-and-factors.md).

## multiple_comparison

Controls multiple-testing adjustment in applicable statistical functions. See also:
[Statistics options](../parameters/statistics-options.md).

## force_nonparametric

Forces nonparametric testing where supported. See also:
[Statistics options](../parameters/statistics-options.md).

## posthoc_correction

Controls correction for posthoc comparisons where supported. See also:
[Statistics options](../parameters/statistics-options.md).

## roi

Selects a region or ROI base for data extraction or plotting. See also:
[ROI parameters](../parameters/roi.md).

## save

Whether a function should write outputs to disk. See also:
[Saving parameters](../parameters/saving.md).

## save_path

An explicit destination path for saved output where supported. See also:
[Saving parameters](../parameters/saving.md).

## output_dir

An output directory for pipeline or modelling functions. See also:
[Model sweep outputs](../outputs/model-sweep-outputs.md).

## run_label

A label used to name or organize a saved run. See also:
[Saving parameters](../parameters/saving.md).

## if_exists

An overwrite policy used by some output-producing functions. See also:
[Saving parameters](../parameters/saving.md).

## cv

Cross-validation setting, such as `stratified5`, `stratifiedN`, or `loo` in
classification sweeps. See also: [Model options](../parameters/model-options.md).

## scoring

The metric used to rank model outputs. See also:
[Model options](../parameters/model-options.md).

## model_preset

Classifier-grid size for `iterative_model_sweep`: `ultra_compact`, `compact`,
or `full`. See also: [Model options](../parameters/model-options.md).

## search_strategy

Feature-subset search mode, usually `exhaustive` or `beam` for model sweeps.
See also: [Model options](../parameters/model-options.md).

## n_jobs

Number of parallel scoring workers for supported model functions. See also:
[Model options](../parameters/model-options.md).

## checkpoint_every

How often model sweeps write partial score checkpoints. See also:
[Model sweep outputs](../outputs/model-sweep-outputs.md).

## resume

Whether a model sweep should continue from a matching partial checkpoint. See also:
[Model sweep outputs](../outputs/model-sweep-outputs.md).

## random_state

A seed used to make stochastic model steps reproducible. See also:
[Model options](../parameters/model-options.md).

## image_backend

The image reader backend used by image plotting functions. See also:
[Image panels](../plot-types/image-panels.md).

## fast_loading

Image plotting option that trades full-resolution loading for faster previews
where supported. See also: [Image panels](../plot-types/image-panels.md).

## preview_max_dim

Maximum preview dimension for faster image rendering. See also:
[Image panels](../plot-types/image-panels.md).

## markers

The marker or channel names requested by an image, summary, or colocalisation
plot. See also: [Markers](../object-types/markers.md).
