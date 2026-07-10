# Parameters Folder Context

This folder explains common parameter names and option vocabularies used across
many PyFLASH functions. It should reduce repeated explanations in individual
function pages.

## What Belongs Here

Add pages for reusable parameters or parameter families, such as:

- `input-objects.md`: common meanings of `experiment`, `batch`, `source`, and
  `batch_or_df`.
- `column-selection.md`: `data_cols`, `data_col_contains`, `data_col_regex`,
  `data_col_exclude`, legacy column aliases, and predictor selection variants.
- `specificity.md`: `filter_by`, legacy `specificity`, row-filter queues, and
  path naming.
- `roi.md`: ROI bases, ROI queues, region names, and image ROI names.
- `conditions-and-factors.md`: `groups`, `group_list`, `group_col`,
  `group_cols`, `split_by`, legacy condition/factor aliases, comparisons,
  `multiple_comparison`, and crossed designs.
- `saving.md`: `save`, `save_path`, `output_dir`, `run_label`, `dpi`, and
  overwrite behavior.
- `statistics-options.md`: `force_nonparametric`, `posthoc`,
  `posthoc_correction`, `ns`, `alpha`, and correction names.
- `model-options.md`: `cv`, `scoring`, `model_preset`, `model_families`,
  `search_strategy`, `n_jobs`, and `random_state`.

## Page Shape

Use this shape:

```markdown
# Parameter or option family

## Summary
What this option controls.

## Used By
Functions or plot families that use this option.

## Accepted Values
Tables or examples of valid values.

## Examples
Short examples showing common and edge-case usage.

## Interactions
Other parameters that change the behavior.

## Common Errors
Misuse patterns and how to fix them.

## See Also
Related function, object, data-structure, or workflow pages.
```

## Source Checks

Use signatures and implementation details from:

- `PyFLASH/plotting.py`
- `PyFLASH/pipeline.py`
- `PyFLASH/modelling.py`
- `PyFLASH/exclusions.py`
- `PyFLASH/utils.py`
- `PyFLASH/stats.py`
- `PyFLASH/stats_extra.py`

Do not list every parameter on every function. Explain reusable patterns.
