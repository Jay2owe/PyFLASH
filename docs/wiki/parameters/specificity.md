# Filter By And Row Filters

## Summary

`filter_by` restricts rows before a plot, pipeline, model, or outlier
detection step runs. Older code and some internal APIs call the same concept
`specificity`.

A single row filter keeps one subset. A filter queue runs the same
analysis for several subsets.

## Used By

- Summary plots such as [`plot_mean_bars`](../functions/plot_mean_bars.md),
  [`plot_matrices`](../functions/plot_matrices.md),
  [`plot_regressions`](../functions/plot_regressions.md),
  [`plot_radar`](../functions/plot_radar.md),
  [`plot_volcano`](../functions/plot_volcano.md),
  [`plot_superplot`](../functions/plot_superplot.md), and
  [`plot_group_matrix`](../functions/plot_group_matrix.md).
- Pipelines such as [`correlation`](../functions/correlation.md),
  [`adjusted_correlation`](../functions/adjusted_correlation.md),
  [`data_overview`](../functions/data_overview.md),
  [`group_comparison`](../functions/group_comparison.md),
  [`linear_model`](../functions/linear_model.md), and
  [`rhythm`](../functions/rhythm.md).
- Model sweeps and linear-model helpers.
- Outlier and manual exclusion helpers.
- Plot spec files and UI requests, where `filter_by` mappings and lists are
  converted into the internal row-filter objects.

## Accepted Values

| Form | Example | Meaning |
|---|---|---|
| `None` | `filter_by=None` | Do not filter rows. |
| Mapping with one key | `filter_by={"Region": "SCN"}` | Preferred public form. Normalized internally to a tuple. |
| Mapping with several keys | `filter_by={"Sex": "Female", "Region": "SCN"}` | AND filter: keep rows matching every key. |
| List of mapping filters | `filter_by=[{"Sex": "Female", "Region": "SCN"}, {"Sex": "Male", "Region": "SCN"}]` | Queue mode with multi-key AND filters. |
| Tuple/list with one key and one value | `specificity=("Time", "WeekEight")` | Legacy/internal form. Keep rows where the `Time` column matches `WeekEight`. |
| Tuple/list with one key and several values | `specificity=("Time", "WeekFour", "WeekEight")` | Legacy/internal form. Keep rows where `Time` is any listed value. Nested lists are flattened. |
| List of tuples or mappings | `specificity=[("Time", "WeekFour"), ("Time", "WeekEight")]` | Legacy/internal queue form where supported. |

String and categorical columns are matched after trimming whitespace and
case-folding. Numeric columns use normal `isin` matching. If the requested
column cannot be resolved, the low-level filter leaves the DataFrame unchanged;
function-level validation may still fail later if no usable data remain.

## Examples

Single-column mapping:

```python
from PyFLASH.plotting import plot_mean_bars

plot_mean_bars(
    batch,
    data_cols=["GFAP_Count"],
    filter_by={"Time": "WeekEight"},
    save=False,
)
```

Multi-key mapping:

```python
from PyFLASH import correlation

result = correlation(
    df,
    data_cols=["GFAP_Count"],
    against_data_cols=["Age"],
    group_col="Diagnosis",
    subject_col="AnimalName",
    filter_by={"Sex": "Female", "Region": "SCN"},
    tests=("pearsonr",),
    save=False,
)
```

Queue mode:

```python
from PyFLASH import data_overview

result = data_overview(
    batch,
    data_cols=["GFAP_Count", "Iba1_Count"],
    filter_by=[{"Diagnosis": "Control"}, {"Diagnosis": "AD"}],
    run_label="diagnosis_queue",
)
```

## Interactions

`specificity` is the legacy/internal alias for `filter_by`. Do not pass both
with different values.

Specificity is a row filter. It is different from:

| Parameter | Layer |
|---|---|
| [`roi`](roi.md) | Chooses an ROI base from `experiment.summaries`. |
| [`split_by`](conditions-and-factors.md) | Chooses analysis groups or panels after filtering. |
| [`data_cols`](column-selection.md) | Chooses metric columns, not rows. |

Queue behavior depends on the function:

- Standalone plots usually return a dictionary keyed by the individual
  filter values.
- Pipelines write one shared run folder for the queue. Each queued filter's files
  are distinguished by a concise filter filename tag, and the manifest
  includes a `conditions` ledger.
- Pipeline queue tags are checked for filename collisions. Values such as
  `"A-D"` and `"AD"` can collide after filename sanitizing and will raise.

Filename tags are compact forms such as `Diagnosis.AD` or
`Sex.Female+Region.SCN`. Config aliases may shorten those tokens in pipeline
outputs.

## Common Errors

- Writing `filter_by=("Sex")`. This is just a string-like value, not a
  `(column, value)` pair.
- Expecting `filter_by={"Sex": "Female", "Region": "SCN"}` to run two analyses.
  It is one AND filter. Use a list of mappings for queue mode.
- Filtering on a display label instead of a real summary-table column.
- Using `filter_by` when you meant `roi="SCN"`. ROI bases and row-level
  `Region` values are separate concepts.
- Passing both `filter_by` and `specificity` with different values.

## See Also

- [Summary table](../data-structures/summary-table.md)
- [ROI selection](roi.md)
- [Groups and factors](conditions-and-factors.md)
- [Pipeline manifests](../data-structures/pipeline-manifests.md)
