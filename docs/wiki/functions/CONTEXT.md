# Functions Folder Context

This folder holds detailed pages for public PyFLASH callables.

## Page Rule

Use one file per callable:

```text
functions/function_name.md
```

Use snake_case filenames that match the callable name. Keep each page focused on
that callable; move shared explanations to `../concepts/` and link to them.

## Required Format

Follow [Documentation standard](../documentation-standard.md):

- Summary
- Signature
- Input Object Types
- Parameters
- Returns
- Saved Outputs
- Examples
- Notes
- See Also

Every page must state:

- expected input object type;
- important parameters and accepted values;
- Python return value;
- files and folders saved when `save=True`;
- at least one minimal example;
- at least one realistic example;
- how to inspect or reuse the returned object.

## Source Checks

Before documenting a callable, inspect its real signature and behavior.

Useful source locations:

- Top-level public names: `PyFLASH/__init__.py`
- Registered plot and pipeline names: `PyFLASH/spec.py::PLOT_REGISTRY`
- Plot functions: `PyFLASH/plotting.py`
- Pipeline functions: `PyFLASH/pipeline.py`
- Batch creation: `PyFLASH/factory.py`
- Conditions: `PyFLASH/conditions.py`
- Modelling: `PyFLASH/modelling.py`
- Exclusions: `PyFLASH/exclusions.py`
- UI service functions: `PyFLASH/ui/services.py`

Use tests to confirm edge cases and saved output names where possible.

## Plot Function Notes

For plotting pages, document these patterns when present:

- `data_cols`, `data_col_contains`, `data_col_regex`, and `data_col_exclude`
- `filter_by` row filters and queue mode; mention `specificity` only as a legacy/internal alias
- `roi` selection and ROI queue mode
- `save`, `save_path`, `output_dir`, `dry_run`, and returned figures or tables
- factor-based grouping for crossed designs
- whether the plot name appears in `PLOT_REGISTRY`
- whether the plot emits structured results through the describe/report layer

Keep saved-output wording separate from return-value wording.

## Planned Coverage

High-priority function pages:

- Core loading and saving: `create_batch`, `save_state`, `load_state`,
  `normalize_paths`, `from_dataframe`
- Conditions: `ConditionBuilder`, `condition`, `multiCondition`,
  `conditionList`, `zipConditions`, `zipConditionLists`
- Pipelines: `correlation`, `adjusted_correlation`, `data_overview`,
  `group_comparison`, `linear_model`, `rhythm`
- Modelling: `iterative_best_fit`, `iterative_model_sweep`,
  `run_linear_model_pipeline`
- Exclusions: `exclude_outliers`, `mark_outliers`, `apply_exclusions`,
  `mark_exclusions`, `exclude_animals`, `mark_animals`
- Plot registry callables listed in `PyFLASH/spec.py::PLOT_REGISTRY`
- UI service functions only when they are stable enough for developer users

When adding one of these pages, also add a link from
[API reference](../api-reference.md).
