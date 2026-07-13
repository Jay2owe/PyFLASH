# Exclusion Helpers

## Summary

Exclusion helpers create auditable cleaned copies of PyFLASH objects. They can
detect outlier cells, record manual exclusions, exclude whole subjects, or mark
candidate exclusions first and apply them later.

The original object is not modified. Each helper returns a shallow copy with
copied summary tables, a `.exclusions` ledger, and usually an
`.exclusion_summary` dictionary. Excluded cells are written as reason-coded
`EXCLUDED_...` sentinel strings by default, and downstream numeric paths treat
those sentinels as analysis-missing.

## Signature

```python
exclude_outliers(
    experiment,
    *,
    filtered_columns=None,
    data_cols=None,
    column_strings=None,
    regex_string=None,
    exclude="",
    data_col_contains=None,
    data_col_regex=None,
    data_col_exclude=None,
    by="all",
    factor=None,
    split_by=None,
    specificity=None,
    filter_by=None,
    scope="cell",
    methods=("rout",),
    iqr_k=1.5,
    mad_threshold=3.5,
    rout_q=1.0,
    animal_min_flags=2,
    subject_min_flags=None,
    fill=None,
    roi=None,
    outliers=None,
    save=False,
    run_label=None,
    verbose=True,
)

mark_outliers(...same parameters...)

apply_exclusions(
    experiment,
    *,
    cells=None,
    animals=None,
    subjects=None,
    columns=None,
    reason=None,
    kind="manual",
    fill=None,
    roi=None,
)

mark_exclusions(
    experiment,
    *,
    cells=None,
    animals=None,
    subjects=None,
    columns=None,
    reason=None,
    roi=None,
)

exclude_subjects(
    experiment,
    subjects,
    *,
    reason=None,
    columns=None,
    roi=None,
    fill=None,
    save=False,
    run_label=None,
    verbose=True,
)

mark_subjects(experiment, subjects, *, reason=None, columns=None, roi=None, verbose=True)

# Legacy aliases:
exclude_animals(experiment, animals, ...)
mark_animals(experiment, animals, ...)
```

## Input Object Types

| Object type | Accepted? | Notes |
|---|---:|---|
| `Batch` | Yes | Main input for full workflows. Must expose `summary` or `summaries`; nested heavy data is shared by the returned shallow copy. |
| `Experiment` | Yes | Works on the selected ROI summary table. |
| `MiniExperiment` | Yes | Works when it exposes a subject-level summary table with `AnimalName`. |
| `DataFrameExperiment` | Yes | Works for summary-table exclusions created from tabular data. |
| `pandas.DataFrame` | No | These helpers expect an experiment-like object with `.summary` or `.summaries`. Wrap raw tables with [`from_dataframe`](from_dataframe.md). |

## Parameters

| Parameter | Type | Default | Meaning |
|---|---|---:|---|
| `experiment` | PyFLASH object | required | Object whose summary table should be marked or cleaned. |
| `data_cols` | list-like or `None` | `None` | Exact metric columns considered for outlier detection. Alias: `filtered_columns`. |
| `data_col_contains` | list-like, `str`, or `None` | `None` | Include columns whose names contain these substrings. Alias: `column_strings`. |
| `data_col_regex` | `str` or `None` | `None` | Include columns matching this regular expression. Alias: `regex_string`. |
| `data_col_exclude` | `str` or list-like | `None` | Exclude matching column names after selection. Alias: `exclude`, whose legacy default is `""`. |
| `by` | `str` | `"all"` | Outlier grouping mode passed to `data_overview` detection. |
| `factor` | `str` or `None` | `None` | Factor column or condition factor for grouped outlier detection. |
| `split_by` | `str` or `None` | `None` | Public grouping alias resolved to `by` or `factor`. |
| `filter_by` | tuple, list, dict, or `None` | `None` | Row filter before detection. Alias: `specificity`. |
| `scope` | `str` | `"cell"` | Exclusion scope for detected outliers. |
| `methods` | tuple/list of `str` | `("rout",)` | Outlier rules passed to `data_overview`. |
| `iqr_k` | `float` | `1.5` | IQR multiplier for IQR outlier detection. |
| `mad_threshold` | `float` | `3.5` | Modified z-score threshold for MAD outlier detection. |
| `rout_q` | `float` | `1.0` | ROUT false discovery rate percentage. |
| `subject_min_flags` | `int` or `None` | `None` | Minimum number of flagged metrics required to blank a subject across metrics. Alias: `animal_min_flags`, retained because the compatibility scope is still `scope="animal"`. |
| `outliers` | `pandas.DataFrame` or `None` | `None` | Precomputed outlier table, usually from `data_overview`, to skip re-detection. |
| `cells` | iterable of `(subject, column)` or `None` | `None` | Explicit manual cells for `apply_exclusions` or `mark_exclusions`. |
| `subjects` | `str`, list-like, dict, or `None` | `None` | Whole subjects to exclude or mark; dict values are per-subject reasons. Alias: `animals`. |
| `columns` | list-like or `None` | `None` | Metric columns affected by whole-subject manual exclusions. `None` means every metric column. |
| `reason` | `str` or `None` | `None` | Manual exclusion reason stored in the ledger and sentinel token. |
| `kind` | `str` | `"manual"` | Ledger kind for explicit `apply_exclusions`; ordinary users usually leave this alone. |
| `fill` | any value or `None` | `None` | Replacement value. `None` uses `EXCLUDED_OUTLIER...` or `EXCLUDED_MANUAL...`; pass `np.nan` for plain missing values. |
| `roi` | `str`, list-like, or `None` | `None` | ROI summary key to operate on. A single ROI is resolved for each helper call. |
| `save` | `bool` | `False` | Save the exclusion ledger CSV for helpers that expose this option. |
| `run_label` | `str` or `None` | `None` | Label used in saved exclusion CSV filenames. |
| `verbose` | `bool` | `True` | Print a compact summary of marked or excluded cells. |

## Parameter Options

### `scope` options

| Option | Behavior |
|---|---|
| `"cell"` (default) | Blank each flagged metric cell. |
| `"animal"` | Blank every selected metric for subjects flagged on enough metrics. This value is retained for compatibility with older naming. |

### `methods` options

| Option | Behavior |
|---|---|
| `"rout"` (default) | Use ROUT outlier detection with `rout_q`. |
| `"mad"` | Use modified-z-score outlier detection with `mad_threshold`. |
| `"iqr"` | Use interquartile-range outlier detection with `iqr_k`. |

## Returns

| Return value | Type | Meaning |
|---|---|---|
| `cleaned` | same object family as input | Returned by `exclude_outliers`, `apply_exclusions`, `exclude_subjects`, and `exclude_animals`; summary cells are filled with exclusion sentinels or `fill`. |
| `marked` | same object family as input | Returned by `mark_outliers`, `mark_exclusions`, `mark_subjects`, and `mark_animals`; summary data is unchanged, but `.exclusions` records what would be applied. |
| `.exclusions` | `pandas.DataFrame` | Ledger attached to the returned object. Important columns include `AnimalName`, `column`, `original_value`, `kind`, `reason`, `scope`, and `fill`. |
| `.exclusion_summary` | `dict` | Compact summary attached to the returned object, with counts and method/reason metadata. |

## Saved Outputs

Most exclusion helpers only return Python objects. Persist the cleaned or marked
object with [`save_state`](save_state.md) if needed.

When `save=True` is available and at least one cell is affected, PyFLASH writes
one CSV ledger:

```text
<data_path or parent-of-fig_path>/Exclusions/exclusions_<run_label>.csv
```

If `run_label=None`, the default label is based on the exclusion scope and ROI,
such as `cell_SCN` or `animal_SCN`.

## Examples

### Exclude detected outlier cells

```python
from PyFLASH import exclude_outliers

cleaned = exclude_outliers(
    batch,
    data_cols=["GFAP Volume", "Iba1 Volume"],
    methods=("mad",),
    scope="cell",
    verbose=False,
)

print(cleaned.exclusions[["AnimalName", "column", "reason"]])
```

### Mark first, inspect, then apply

```python
from PyFLASH import apply_exclusions, mark_outliers

marked = mark_outliers(
    batch,
    data_cols=["GFAP Volume"],
    methods=("rout",),
    verbose=False,
)

print(marked.exclusions)
cleaned = apply_exclusions(marked)
```

### Manually exclude one subject

```python
from PyFLASH import exclude_subjects

cleaned = exclude_subjects(
    batch,
    "Mouse_07",
    reason="damaged section",
    columns=["GFAP Volume", "Iba1 Volume"],
    verbose=False,
)
```

### Exclude explicit cells and then reuse the cleaned object

```python
from PyFLASH import apply_exclusions
from PyFLASH.plotting import plot_mean_bars

cleaned = apply_exclusions(
    batch,
    cells=[("Mouse_04", "GFAP Volume"), ("Mouse_09", "Iba1 Volume")],
    reason="manual QC",
)

plot_mean_bars(cleaned, data_cols=["GFAP Volume", "Iba1 Volume"], save=False)
```

### Save the exclusion ledger

```python
from PyFLASH import exclude_outliers

cleaned = exclude_outliers(
    batch,
    data_cols=["GFAP Volume"],
    methods=("mad",),
    save=True,
    run_label="gfap_qc",
)
```

## Notes

- Outlier detection reuses [`data_overview`](data_overview.md), so the detected
  cells match the overview outlier report when the same settings are used.
- `mark_*` helpers do not change summary values. They attach a ledger that can
  be realized later with `apply_exclusions(marked)`.
- `apply_exclusions(experiment)` with no `cells` or `subjects` applies an
  existing `.exclusions` ledger.
- `EXCLUDED_OUTLIER:<rule>` and `EXCLUDED_MANUAL:<reason>` values are counted
  separately from true missing values by quality-control reports and ignored by
  numeric coercion in plots, pipelines, and modelling.
- `scope="cell"` is less aggressive than `scope="animal"`. Use animal scope
  only when a subject should be dropped across many metrics.
- `exclude_subjects` and `mark_subjects` are subject-neutral aliases for
  `exclude_animals` and `mark_animals`. The legacy animal names remain
  supported.
- Because the returned object is a shallow copy, large raw marker tables and
  image metadata are shared by reference, while summary tables are copied.

## See Also

- [Exclusion ledgers](../data-structures/exclusion-ledgers.md)
- [Column selection](../parameters/column-selection.md)
- [Filter By](../parameters/specificity.md)
- [data_overview](data_overview.md)
- [save_state](save_state.md)
- [Statistics look wrong](../troubleshooting/statistics-look-wrong.md)
