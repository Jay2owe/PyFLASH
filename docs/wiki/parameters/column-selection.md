# Column Selection

## Summary

Column-selection parameters choose which metric columns are analysed or plotted.
Use exact column names when you already know them. Use substring or regular
expression discovery when you want PyFLASH to find a family of columns.

## Used By

- Summary plots such as [`plot_mean_bars`](../functions/plot_mean_bars.md),
  [`plot_matrices`](../functions/plot_matrices.md),
  [`plot_rect_matrices`](../functions/plot_rect_matrices.md),
  [`plot_radar`](../functions/plot_radar.md),
  [`plot_volcano`](../functions/plot_volcano.md),
  [`plot_superplot`](../functions/plot_superplot.md), and
  [`plot_effect_forest`](../functions/plot_effect_forest.md).
- Pipelines such as [`correlation`](../functions/correlation.md),
  [`adjusted_correlation`](../functions/adjusted_correlation.md),
  [`data_overview`](../functions/data_overview.md), and
  [`group_comparison`](../functions/group_comparison.md).
- Exclusion helpers that detect outliers with the same column filters.
- Modelling helpers, with predictor-specific variants.
- Plot spec files, where `columns` is also accepted and mapped to the explicit
  data-column selector.

## Accepted Values

| Parameter | Accepted values | Behavior |
|---|---|---|
| `data_cols` | List of exact summary column names. | Preferred public name for exact data columns. Plot wrappers resolve known aliases and raise if no provided name matches. |
| `filtered_columns` | List of exact summary column names. | Legacy/internal alias for `data_cols`. |
| `data_col_contains` | String list. | Preferred public substring selector. |
| `column_strings` | String list such as `["Count", "Volume"]`. | Legacy/internal alias for `data_col_contains`. Matching is substring-based and case-sensitive. |
| `data_col_regex` | Regular expression string. | Preferred public regex selector. |
| `regex_string` | Python regular expression string. | Legacy/internal alias for `data_col_regex`. Selects columns matching the regex when substring filters are not supplied in the shared `get_columns` path. |
| `data_col_exclude` | String or list of strings. | Preferred public exclusion selector. |
| `exclude` | String or list of strings. | Legacy/internal alias for `data_col_exclude`. Removes selected columns whose names contain any exclude token. The default empty string excludes nothing. |

Second-axis matrix and correlation parameters follow the same pattern:

| First-axis option | Second-axis option |
|---|---|
| `data_cols` / legacy `filtered_columns` | `against_data_cols` / legacy `against_columns` |
| `data_col_contains` / legacy `column_strings` | `against_data_col_contains` / legacy `against_column_strings` |
| `data_col_regex` / legacy `regex_string` | `against_data_col_regex` / legacy `against_regex_string` |
| `data_col_exclude` / legacy `exclude` | `against_data_col_exclude` / legacy `against_exclude` |

Predictor-selection variants:

| Function family | Predictor options |
|---|---|
| `iterative_model_sweep` | `possible_predictors`, `data_cols`, `predictors`, or `candidate_predictors` choose the predictor pool; `data_col_contains`/`data_col_regex` filter it; `data_col_exclude` removes name substrings; `excluded_predictors` removes exact names. Legacy aliases include `column_strings`, `regex_string`, and `predictor_exclude`. |
| `iterative_best_fit` | `possible_predictors` plus `data_col_contains`, `data_col_regex`, and `data_col_exclude`. Legacy aliases include `column_strings`, `regex_string`, and `predictor_exclude`. |
| `linear_model` | `predictors` are model terms or column names, not discovered by `column_strings`. |
| Multivariable matrix plots | `predictors` can be a mapping of named predictor sets. |

## Examples

Exact selection:

```python
from PyFLASH.plotting import plot_mean_bars

plot_mean_bars(batch, data_cols=["GFAP_Count", "Iba1_Count"], save=False)
```

Substring selection:

```python
from PyFLASH.plotting import plot_matrices

plot_matrices(
    batch,
    data_col_contains=["_Count", "_VolumeTotal"],
    data_col_exclude=["Raw"],
    save=False,
)
```

Rectangular correlation:

```python
from PyFLASH import correlation

result = correlation(
    batch,
    data_cols=["GFAP_Count", "Iba1_Count"],
    against_data_cols=["Age", "BehaviourScore"],
    tests=("pearsonr",),
    save=False,
)
```

Model predictor pool:

```python
from PyFLASH import iterative_model_sweep

result = iterative_model_sweep(
    batch,
    target="Diagnosis",
    data_col_contains=["_Count", "_VolumeTotal"],
    excluded_predictors=["AnimalName", "Condition"],
    max_features=2,
    save=False,
)
```

## Interactions

Alias pairs cannot disagree. For example, do not pass both
`filtered_columns=["A"]` and `data_cols=["B"]`.

When exact columns are supplied, most plot wrappers use PyFLASH column-key
resolution, which can handle several legacy summary-column aliases. Discovery
filters inspect the actual DataFrame column names.

`data_col_contains` and `data_col_regex` do not always combine the same way. The
shared column resolver prioritizes substring selection when it is supplied;
some modelling predictor filters apply both substring and regex filters to an
explicit predictor pool. Check the function page for exact behavior when using
both at once. Legacy aliases are `column_strings` and `regex_string`.

Column selection happens before numeric validation. A selected column may still
be dropped later if it cannot be converted to numeric for a numeric-only plot or
model.

## Common Errors

- Passing formatted display labels such as `"GFAP volume total"` when the table
  column is actually `GFAP_VolumeTotal`.
- Expecting `exclude="Count"` to remove rows. It removes columns whose names
  contain `"Count"`.
- Supplying a regex while also supplying `data_col_contains` and expecting the
  shared column resolver to intersect them.
- Using a predictor term such as `C(Sex)` in a classifier sweep. Classifier
  sweeps use real DataFrame columns, not formula terms.
- Selecting only string or sentinel-filled columns for numeric plots.

## See Also

- [Summary table](../data-structures/summary-table.md)
- [Filter By and row filters](specificity.md)
- [Model options](model-options.md)
- [Missing columns troubleshooting](../troubleshooting/missing-columns.md)
