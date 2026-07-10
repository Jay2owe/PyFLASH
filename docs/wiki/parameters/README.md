# Common Parameters

## Summary

These pages explain parameter names that appear across many PyFLASH plots,
pipelines, modelling helpers, and exclusion helpers. Function pages still list
the exact signature for each callable; this section explains the reusable
meaning of shared options.

## Used By

Use this section when a function page mentions one of these shared option
families:

| Page | Covers |
|---|---|
| [Input objects](input-objects.md) | `experiment`, `batch`, `source`, `batch_or_df`, raw `DataFrame` input, and object-like requirements. |
| [Column selection](column-selection.md) | `data_cols`, `data_col_contains`, `data_col_regex`, `data_col_exclude`, legacy column selectors, and predictor-selection variants. |
| [Filter By and row filters](specificity.md) | `filter_by`, legacy `specificity`, mapping filters, row-filter queues, and filename tags. |
| [ROI selection](roi.md) | `roi`, ROI bases, ROI queues, and how ROI selection differs from row filters such as `Region`. |
| [Groups and factors](conditions-and-factors.md) | `by`, `factor`, `split_by`, `comparisons`, `multiple_comparison`, and crossed designs. |
| [Saving and run labels](saving.md) | `save`, `save_path`, `output_dir`, `run_label`, `if_exists`, `dpi`, `write_manifest`, and `resume`. |
| [Statistics options](statistics-options.md) | `force_nonparametric`, `posthoc`, `posthoc_correction`, `ns`, `alpha`, `gate`, and correction names. |
| [Model options](model-options.md) | `cv`, `scoring`, `model_preset`, `model_families`, `search_strategy`, `n_jobs`, and `random_state`. |

## Accepted Values

Accepted values are documented in each page. The most important rule is that
newer public aliases are usually accepted alongside older internal names:

| Newer public name | Older/internal name |
|---|---|
| `data_cols` | `filtered_columns` |
| `data_col_contains` | `column_strings` |
| `data_col_regex` | `regex_string` |
| `data_col_exclude` | `exclude` |
| `filter_by` | `specificity` |
| `split_by` | `by` or `factor`, depending on the value |
| `group_col` | `condition_col` |
| `group_cols` | `factor_cols` |
| `subject_col` | `animal_col` |

## Examples

```python
from PyFLASH.plotting import plot_mean_bars

plot_mean_bars(
    df,
    data_cols=["GFAP_VolumeTotal"],
    group_col="Diagnosis",
    subject_col="Animal ID",
    filter_by={"Region": "SCN"},
    split_by="Diagnosis",
    save=False,
)
```

The same call can still be written with older names:

```python
plot_mean_bars(
    df,
    filtered_columns=["GFAP_VolumeTotal"],
    condition_col="Diagnosis",
    animal_col="Animal ID",
    specificity=("Region", "SCN"),
    factor="Diagnosis",
    save=False,
)
```

## Interactions

PyFLASH resolves aliases before analysis. If both names in an alias pair are
given with different non-default values, it raises a `ValueError` instead of
choosing one.

Function support is not universal. For example, many summary plots accept raw
`pandas.DataFrame` input, but manual exclusion helpers expect an experiment-like
object. Check the function page when in doubt.

## Common Errors

- Passing a display label from a figure or Excel export instead of the real
  column name in the summary table.
- Supplying both an old name and a new alias with different values, such as
  `filtered_columns=["A"]` and `data_cols=["B"]`.
- Expecting a row filter, ROI filter, and group split to do the same thing.
  They act at different layers.

## See Also

- [Object model](../object-model.md)
- [Summary table](../data-structures/summary-table.md)
- [Plot spec files](../data-structures/plot-spec-files.md)
- [API reference](../api-reference.md)
