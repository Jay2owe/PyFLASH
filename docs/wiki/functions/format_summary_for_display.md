# format_summary_for_display

## Summary

`format_summary_for_display` returns a display-only copy of a summary table
with human-readable column labels. It is used by the Streamlit-free UI services
and can be useful in scripts before showing or exporting a small preview table.

The function does not change values, row order, or the original DataFrame. It
only replaces column names using PyFLASH's export label rules.

## Signature

```python
format_summary_for_display(summary: pandas.DataFrame) -> pandas.DataFrame
```

## Input Object Types

| Object type | Accepted? | Notes |
|---|---:|---|
| `pandas.DataFrame` | Yes | Required input. Usually pass `batch.summary`, `experiment.summary`, or one entry from `.summaries`. |
| `Batch` | No | Pass `batch.summary` or use a UI/service helper that extracts a summary table first. |
| `Experiment` | No | Pass `experiment.summary` or `experiment.summaries[roi]`. |
| `MiniExperiment` | No | Pass its `summary` table. |
| `DataFrameExperiment` | No | Pass its `summary` table. |

## Parameters

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `summary` | `pandas.DataFrame` | required | Summary table whose columns should be relabelled for display. |

## Returns

| Return value | Type | Meaning |
|---|---|---|
| `display_summary` | `pandas.DataFrame` | Copy of `summary` with display labels as columns. Data values and index are copied from the input. |

## Saved Outputs

No files are written.

## Examples

### Relabel one loaded batch summary

```python
from PyFLASH import format_summary_for_display

display = format_summary_for_display(batch.summary)
print(display.head())
```

### Keep raw and display versions separate

```python
from PyFLASH import format_summary_for_display

raw = batch.summary
display = format_summary_for_display(raw)

print(raw.columns[:3])
print(display.columns[:3])
```

### Use with one ROI-specific summary

```python
from PyFLASH import format_summary_for_display

scn_summary = batch.summaries["SCN"]
scn_display = format_summary_for_display(scn_summary)
```

### Save a preview table yourself

```python
from PyFLASH import format_summary_for_display

display = format_summary_for_display(batch.summary)
display.to_csv("outputs/summary_display_preview.csv", index=False)
```

## Notes

- This is a display helper, not a schema conversion. Use raw column names when
  passing `data_cols`, `filtered_columns`, model variables, or plot-spec
  columns back into PyFLASH functions.
- The mapping first tries the immunofluorescence summary labels, then behavior
  labels, then a fallback label for unregistered summary columns.
- Unregistered fallback labels split underscores and camel-case-like names into
  readable text.
- If `summary` is not a `pandas.DataFrame`, the function raises `TypeError`.
- The returned table may contain duplicate display labels if two raw columns
  map to the same readable name. Keep the raw summary for programmatic work.

## See Also

- [Summary table](../data-structures/summary-table.md)
- [API reference](../api-reference.md)
- [Input objects](../parameters/input-objects.md)
- [Excel workbooks](../outputs/excel-workbooks.md)
